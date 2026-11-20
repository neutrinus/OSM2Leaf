# EXP-2026-11-20-H89: the 1,259 `fn_match` NOMATCH — 40 % same code in the sample, 60 % real code differences

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 head), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`;
  `archive/us256.img` (US 2011 head), SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`
  (both git-ignored). Module `Navi.exe`, build A (`0x200200`) in both.
- **Tools:** python3 3.13.18; repo tools `tools/nomatch_census.py` (new),
  `tools/fn_match.py` (unchanged), `tools/sh4dis.py`, `tools/cerom.py`
- **Claims:** C-4120–C-4126
- **Supersedes:** none
- **Superseded by:** none

## Question

Of the `NOMATCH 1259` functions the M1.22b census leaves (C-3626), are they
real US rewrites or a second class the matcher misses?

## Hypothesis

Exploratory, following the M1.22b shape: classify a sample by disassembly and
let the classes fall out. **Falsifier** (stated before the run): a function
counts as a *matcher miss* only if its US counterpart, found **without** any
matcher hash, has the same instruction stream (pool slots removed); if every
sampled pair has a differing instruction or no counterpart, the 1,259 are
rewrites and no matcher class exists. Conversely a "rewrite" must show a
differing instruction in `sh4dis` output, not only a differing literal.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img`, `archive/us256.img` |
| SHA-256 | `92aa525d…007f9`, `70d945d8…04da` |
| Corpus | `Navi.exe` pdata: EU `7596`, US `7520` records; NOMATCH `1259` |
| Sample | seed `89`, size `40`, `random.Random(89).sample` over the NOMATCH list in pdata order |
| Repo tool | `tools/nomatch_census.py` (produces every number below) |

## Method

1. **Sample and hash.** The two heads above; `fn_match.Matcher` reads each
   `Navi.exe` code section through `cerom.py`.
2. **Commands.**

   ```bash
   python3 tools/nomatch_census.py --selftest
   # the 40-row sample with both controls
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --seed 89 --size 40
   # tool-only cross-check over all 1259 (distribution only)
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all
   # precheck: one sampled VA is NOMATCH with diff null
   python3 tools/fn_match.py match archive/head256.img archive/us256.img \
       --module Navi.exe --va 0x003c0108 --json /tmp/x.json
   # raw halfword compare of one pair, with pool-slot and phantom notes
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --pair 0x0033d00c:0x0036bb5c
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --pair 0x003c0108:0x003eef2c
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --pair 0x003911b8:0x003bfa54
   # UNPAIRED rows: fall back over every US record, claimed ones too
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --global-all
   # whole-pipeline negative controls (navigator round, see Corrections)
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all --anchor-shift 1 --no-global
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all --anchor-shift 1
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all --anchor-shuffle 7 --no-global
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all --anchor-shuffle 7
   # independent instruction check of a pair (EU, then US)
   python3 tools/sh4dis.py archive/head256.img Navi.exe --va 0x003c0108 --count 48
   python3 tools/sh4dis.py archive/us256.img Navi.exe --va 0x003eef2c --count 48
   ```

   The census inside the tool is `Matcher.verdict()` over every EU function,
   the same path as the M1.22b script. **Pairing does not use any matcher
   hash:** the nearest matched EU neighbours (`UNIQUE`/`DIFFERENT`/
   `CALLORDER`, 5819 records) on each side bracket a US pdata range; equal
   EU/US gap sizes give one candidate at the same offset (`anchor`), unequal
   ones give every US record of the gap (`gap`, the 64 nearest the
   proportional index), and the most similar candidate is kept. Below
   similarity `0.5` the tool searches all `1708` US records no matcher
   verdict claims (`+global`, length within 0.7×–1.43×); none above `0.5`
   is `UNPAIRED`. Classes are computed on the *body*: halfwords with the
   function's own pool slots removed (found by a forward pass, see below) and
   trailing padding dropped; branch and `mov.x @(disp,PC)` displacements are
   masked as in `fn_match`. Class order: `TWIN` (matcher `code_digest` equal,
   ≥2 US twins), `PHANTOM-SLOT`, `POOL-LAYOUT`, `REGALLOC`, `IMMEDIATE`,
   `OPERANDS`, `REORDER`, `EDIT` (ratio ≥0.9), `REWRITE` (0.5–0.9), `UNPAIRED`
   (definitions in the tool's docstring).
3. **Controls.** *Anchor (positive)*: 40 `UNIQUE` functions (seed 89),
   each with its own anchor removed, must be paired with the matcher's own US
   function. *Classifier (negative)*: the same 40 EU bodies against the
   **next** US record must not be classed as same code; this tests
   `classify_bodies`, not the pairing. *Pipeline (negative)*: the whole
   NOMATCH run with every anchor moved one US record (`--anchor-shift 1`)
   or with the anchors' US indexes shuffled (`--anchor-shuffle 7`), each
   with and without the `+global` fallback. Selftest: 20 synthetic cases,
   one per class plus the phantom-slot case and the anchor/gap/edge pairing.
4. **Scope.** `Navi.exe` build A only, pdata functions only (leaves are not
   in the 1259). The 40 sampled rows are the result; the `--all` run is a
   tool-only cross-check, not hand-checked. `fn_match.py` is not changed
   (task Scope); the two cheap fixes are new tasks.
5. **Falsifier.** As in the Hypothesis.

## Observations

Precheck: `fn_match … --va 0x003c0108 --json` prints `NOMATCH` and the JSON
row carries `"diff": null`; the in-tool census prints
`UNIQUE 2392  DIFFERENT 3214  CALLORDER 213  AMBIGUOUS 518  NOMATCH 1259  total 7596`.

Sample (seed 89, 40 of 1259). `twins=X/Y`: US functions with the matcher's
`code_digest` / with the forward-pass digest; `ph`: `fn_match`'s slot set
differs from the forward pass in either build; `@+off`: first differing body
instruction (EU offset), as EU word/text and US word/text.

```text
0x0033d00c  1268B anchor        cand=1   twins=0/1 ph -> 0x0036bb5c  1268B PHANTOM-SLOT r=1.000
0x0033de78   446B anchor        cand=1   twins=0/0    -> 0x0036c9ec   288B REWRITE     r=0.561 @+0xa EU[7ff4 add #-12,r15] US[7ff8 add #-8,r15]
0x0034c8a4  1392B anchor        cand=1   twins=0/0 ph -> 0x0037a96c  1424B EDIT        r=0.982 @+0x1a EU[ea00 mov #0,r10] US[d3a1 mov.l @(0x0037ac0c,pc),r3]
0x00386a90   196B gap           cand=9   twins=0/0    -> -                  UNPAIRED    r=0.296 @+0x0 EU[4f22 sts.l pr,@-r15] US[2f86 mov.l r8,@-r15]
0x0038921c   276B gap           cand=11  twins=0/0    -> -                  UNPAIRED    r=0.310 @+0x4 EU[2fa6 mov.l r10,@-r15] US[4f22 sts.l pr,@-r15]
0x0038a5ac   188B gap           cand=14  twins=0/0    -> -                  UNPAIRED    r=0.247 @+0x4 EU[4f22 sts.l pr,@-r15] US[2fa6 mov.l r10,@-r15]
0x0038bd30   116B gap           cand=4   twins=0/0    -> -                  UNPAIRED    r=0.333 @+0x8 EU[9128 mov.w @(0x0038bd8c,pc),r1] US[7ff0 add #-16,r15]
0x0038e284   364B gap           cand=1   twins=0/0    -> 0x003bcd70   364B EDIT        r=0.952 @+0x116 EU[e300 mov #0,r3] US[e200 mov #0,r2]
0x0038e4d4    16B gap           cand=8   twins=18/18    -> 0x003bcf54    16B TWIN        r=1.000
0x003911b8   548B gap           cand=50  twins=0/0    -> 0x003bfa54   548B IMMEDIATE   r=0.996 @+0x30 EU[e14b mov #75,r1] US[e14c mov #76,r1]
0x003920a8   792B gap           cand=50  twins=0/0    -> 0x003c08bc   796B EDIT        r=0.971 @+0x6a EU[4200 shll r2] US[4208 shll2 r2]
0x003c0108    96B anchor        cand=1   twins=2/2    -> 0x003eef2c    96B TWIN        r=1.000
0x003c2608    96B anchor        cand=1   twins=2/2    -> 0x003f1380    96B TWIN        r=1.000
0x003c3684   376B anchor        cand=1   twins=2/2    -> 0x003f22cc   376B TWIN        r=1.000
0x003c38d0   164B anchor        cand=1   twins=3/3    -> 0x003f2518   164B TWIN        r=1.000
0x003c3a34   164B gap           cand=1   twins=3/3    -> 0x003f267c   164B TWIN        r=1.000
0x003c9bb0   208B anchor        cand=1   twins=2/2    -> 0x003f846c   208B TWIN        r=1.000
0x003dec70  1692B gap           cand=0   twins=0/0 ph -> -                  UNPAIRED    r=-
0x003fd390   312B gap           cand=1   twins=0/0    -> 0x00425564   312B IMMEDIATE   r=0.993 @+0xe0 EU[e0b4 mov #-76,r0] US[e0ac mov #-84,r0]
0x0041253c    84B anchor        cand=1   twins=0/0    -> 0x0043a314    76B REWRITE     r=0.818 @+0x1c EU[890c bt 0x00412574] US[8b02 bf 0x0043a338]
0x00416d40   372B anchor        cand=1   twins=0/0    -> 0x0043ea74   420B EDIT        r=0.909 @+0x12 EU[6a53 mov r5,r10] US[6d53 mov r5,r13]
0x00446344  1424B anchor        cand=1   twins=0/1 ph -> 0x004706f4  1424B PHANTOM-SLOT r=1.000
0x0045eb44   160B anchor        cand=1   twins=0/0    -> 0x004884c8   160B IMMEDIATE   r=0.971 @+0x1c EU[853c mov.w @(24,r3),r0] US[853a mov.w @(20,r3),r0]
0x0046d464  2464B anchor        cand=1   twins=0/1 ph -> 0x004959c4  2464B PHANTOM-SLOT r=1.000
0x0047c2a8   948B gap           cand=0   twins=0/0    -> -                  UNPAIRED    r=-
0x004853fc  1452B anchor        cand=1   twins=0/0 ph -> 0x004a7c18  1408B EDIT        r=0.974 @+0x7c EU[d392 mov.l @(0x004856c4,pc),r3] US[4911 cmp/pz r9]
0x0048715c   240B anchor        cand=1   twins=0/0    -> 0x004aa0f8   216B EDIT        r=0.946 @+0x88 EU[d214 mov.l @(0x00487238,pc),r2] US[d30f mov.l @(0x004aa1c0,pc),r3]
0x00491a18   292B gap           cand=0   twins=0/0    -> -                  UNPAIRED    r=-
0x004982c0   260B anchor        cand=1   twins=0/0    -> 0x004bb314   260B EDIT        r=0.959 @+0x3a EU[e501 mov #1,r5] US[e500 mov #0,r5]
0x004c8678   104B gap           cand=12  twins=18/18    -> 0x004eb6e4   104B TWIN        r=1.000
0x004cc0a0   120B anchor        cand=1   twins=0/0    -> 0x004eefc8   120B IMMEDIATE   r=0.980 @+0x24 EU[e20c mov #12,r2] US[e20b mov #11,r2]
0x004cc810    48B anchor        cand=1   twins=2/2    -> 0x004ef738    48B TWIN        r=1.000
0x004e3658   252B gap           cand=2   twins=0/0    -> 0x00505204   200B REWRITE     r=0.534 @+0xc EU[6853 mov r5,r8] US[6953 mov r5,r9]
0x004e570c   436B gap           cand=64  twins=0/0    -> -                  UNPAIRED    r=0.102 @+0x0 EU[2fe6 mov.l r14,@-r15] US[2f86 mov.l r8,@-r15]
0x004e989c   216B anchor        cand=1   twins=2/2    -> 0x005096e4   216B TWIN        r=1.000
0x004fbd00    52B anchor        cand=1   twins=2/2    -> 0x0051e14c    52B TWIN        r=1.000
0x0052ba30   104B gap           cand=7   twins=0/0    -> 0x0054dd90   120B REWRITE     r=0.695 @+0xa EU[6a53 mov r5,r10] US[6963 mov r6,r9]
0x00538654    88B anchor        cand=1   twins=4/4    -> 0x0055a888    88B TWIN        r=1.000
0x0053f5e8    60B anchor        cand=1   twins=12/12    -> 0x005618e4    60B TWIN        r=1.000
0x00552f74   872B gap           cand=8   twins=0/0 ph -> 0x00576528   980B REWRITE     r=0.577 @+0x20 EU[1e33 mov.l r3,@(12,r14)] US[1e34 mov.l r3,@(16,r14)]
# classes: TWIN 13  PHANTOM-SLOT 3  POOL-LAYOUT 0  REGALLOC 0  IMMEDIATE 4  OPERANDS 0  REORDER 0  EDIT 7  REWRITE 5  UNPAIRED 8
#   anchor          22: TWIN 10  PHANTOM-SLOT 3  IMMEDIATE 2  EDIT 5  REWRITE 2
#   gap             18: TWIN 3  IMMEDIATE 2  EDIT 2  REWRITE 3  UNPAIRED 8
# same code (TWIN+PHANTOM-SLOT+POOL-LAYOUT): 16  operand-only (REGALLOC+IMMEDIATE+OPERANDS): 4  instruction changes (REORDER+EDIT+REWRITE): 12  unpaired: 8  of 40
# US records named by more than one row: 0 (rows 0)
# anchor control: 40 UNIQUE (seed 89), own anchor removed: the anchor names the matcher's US function in 38
# classifier control: same EU body vs the next US record: EDIT 2  REWRITE 1  UNPAIRED 37
# forward-pass digest unique in US: 3 of 40 (the anchor pairs the same US function in 3)
```

Population cross-check (`--all`, tool only):

```text
# classes: TWIN 219  PHANTOM-SLOT 141  POOL-LAYOUT 0  REGALLOC 0  IMMEDIATE 80  OPERANDS 1  REORDER 0  EDIT 157  REWRITE 317  UNPAIRED 344
#   anchor         729: TWIN 188  PHANTOM-SLOT 131  IMMEDIATE 62  OPERANDS 1  EDIT 120  REWRITE 183  UNPAIRED 44
#   anchor+global   10: REWRITE 10
#   gap            467: TWIN 27  PHANTOM-SLOT 7  IMMEDIATE 17  EDIT 32  REWRITE 84  UNPAIRED 300
#   gap+global      53: TWIN 4  PHANTOM-SLOT 3  IMMEDIATE 1  EDIT 5  REWRITE 40
# US records named by more than one row: 30 (rows 63)
# same code (TWIN+PHANTOM-SLOT+POOL-LAYOUT): 360  operand-only (REGALLOC+IMMEDIATE+OPERANDS): 81  instruction changes (REORDER+EDIT+REWRITE): 474  unpaired: 344  of 1259
# forward-pass digest unique in US: 141 of 1259 (the anchor pairs the same US function in 141)
```

Whole-pipeline negative controls (`--all`, the `# same code` and `# classes`
lines; added in the navigator round):

```text
--anchor-shift 1 --no-global : same code 73 (TWIN 69, 49 of them anchor; PHANTOM-SLOT 4)  IMMEDIATE 21  EDIT 37  REWRITE 105  UNPAIRED 1023
--anchor-shift 1             : same code 158 (TWIN 123  PHANTOM-SLOT 35)  IMMEDIATE 41  EDIT 82  REWRITE 264  UNPAIRED 713
--anchor-shuffle 7 --no-global: same code 1 (TWIN 1)  REWRITE 30  UNPAIRED 1228
--anchor-shuffle 7           : same code 342 (TWIN 201: 200 via gap+global; PHANTOM-SLOT 141, all via gap+global)  IMMEDIATE 82  EDIT 157  REWRITE 312  UNPAIRED 365
```

Independent `sh4dis` checks (EU 2011 / US 2011, offsets from the start):

- **TWIN** `0x003c0108` (EU) / `0x003eef2c` (US), 96 B each: all 40
  instructions up to `rts` + delay slot are textually identical (same
  registers, same branch offsets `bf/s +0x05`, `bf +0x02`, `bra +0x01`); the
  only differing halfwords are the four pool longwords at `+0x50`…`+0x5f`
  (e.g. `0x01379cd8` / `0x0127e418`); `--pair` prints `raw halfword diffs
  over the common length: 8, in a pool slot of both builds: 8`. The matcher's `code_digest` has 2 US
  twins for this stream, so `_pool_only_twin` returned `None`.
- **PHANTOM-SLOT** `0x0033d00c` / `0x0036bb5c`, 1268 B each: `--pair`
  prints `raw halfword diffs over the common length: 15, in a pool slot of
  both builds: 15` and `US phantom: pool data +0x284 = da3c decodes as
  mov.l @(0x0036bed4,pc),r10 and blanks +0x378 (c11e …)`. The 15 differing
  halfwords (`+0x280…+0x286`, `+0x430…+0x432`, `+0x4dc…+0x4f2`; pointer
  halves such as `0x0032`/`0x0035`) are all forward-pass pool slots in both
  builds. In the US build the pool halfword at `+0x284` is
  `0xda3c`, which decodes as `mov.l @(disp,PC),r10`; `fn_match`'s slot pass
  treats it as a load and blanks `+0x378`, which is the real instruction
  `0xc11e` (`mov.w r0,@(disp,GBR)`) in both builds. A forward pass that
  skips halfwords already marked as pool data blanks nothing there; with it
  the stream has exactly one US twin, the anchored one.
- **IMMEDIATE** `0x003911b8` / `0x003bfa54`, 548 B each: `--pair` prints
  19 raw diffs, 18 in pool slots of both builds, and one instruction:
  `+0x30` `mov #75,r1` / `mov #76,r1`. `0x004cc0a0` / `0x004eefc8`:
  `+0x24` `mov #12,r2` / `mov #11,r2`. `0x0045eb44` / `0x004884c8`: `+0x1c`
  `mov.w @(24,r3),r0` / `mov.w @(20,r3),r0`.
- **EDIT** `0x004982c0` / `0x004bb314`, 260 B each: `+0x3a` `mov #1,r5` /
  `mov #0,r5`, `+0x7a` `cmp/eq #12,r0` / `cmp/eq #11,r0`, and at `+0xd6` the
  US build inserts `mov r2,r0` (`mov #0,r0` becomes `mov #0,r2; mov r2,r0`)
  and drops `mov #1,r0` at `+0xde`. `0x0038e284` / `0x003bcd70`: `r2`/`r3`
  swapped from `+0x116` and `add #36,r1` replaced by `mov.w @(disp,PC),r1`.
- **REWRITE** `0x0041253c` / `0x0043a314`, 84 B / 76 B: the EU
  `cmp/eq #12,r0; bt …; cmp/eq #11,r0; bt …` chain at `+0x1c` is a single
  `bf` plus `mov.l @(disp,PC),r3; bra` in the US build (a case removed).
- **UNPAIRED** 8 rows: no US record in the gap and no unclaimed US record
  reaches similarity 0.5. With `--global-all` (fallback over all 7520 US
  records, claimed ones included) 7 stay `UNPAIRED` and `0x0038a5ac` pairs
  with `0x005023fc` at `0.511` (`REWRITE`, 188 B / 176 B). 7 of the 8 sit in runs of NOMATCH neighbours (e.g.
  `0x0047c2a8`: the 4 records on each side are NOMATCH too).

Gates: `nomatch_census --selftest` → `OK (20 checks, 0 failed)`; gate output
is in the PR body.

## Interpretation

- **FACT:** the sample splits **16 same code / 24 code differs**: 13 `TWIN`
  (10 `anchor`, 3 `gap`) + 3 `PHANTOM-SLOT` (all `anchor`) have an identical
  instruction stream to their paired US counterpart (checked with `sh4dis` for one of each), while 4
  `IMMEDIATE`, 7 `EDIT`, 5 `REWRITE` show a differing instruction and 8 have
  no counterpart at similarity ≥0.5. 95 % Wilson intervals: same code
  26–55 %, code differs 45–74 %.
- **FACT:** two matcher classes exist, both cheap:
  (1) **TWIN** — the masked form stream is shared by ≥2 US functions
  (small accessors, generated-looking stubs), so `_pool_only_twin` refuses;
  address order can pick one (188 of the 219 population TWIN rows are exact
  `anchor` pairs; the tool's pairing is not one-to-one: 30 US records are
  named by more than one row, 63 rows, e.g. EU `0x003c3a34` and `0x003c3ad8`
  both name US `0x003f267c`, so H114 must enforce it).
  (2) **PHANTOM-SLOT** — `fn_match` derives pool slots from every halfword
  that decodes as `mov.x @(disp,PC)`, including pool *data*, and blanks a
  real instruction; a forward pass fixes it (all 141 rows get a unique
  forward-pass digest, and address-order pairing — 131 `anchor`, 10
  `gap`/`gap+global` — names the same US function in 141/141).
- **OBSERVED:** no function differs *only* in register allocation
  (`REGALLOC 0`) or *only* in instruction order (`REORDER 0`), in the sample
  and over all 1259. Register changes do occur together with other edits
  (EU `0x00416d40` `mov r5,r10`→`mov r5,r13` in an `EDIT`; EU `0x0038e284`
  `r2`/`r3` swapped next to a replaced `add #36,r1`; EU `0x004e3658`
  `r8`→`r9` in a `REWRITE`). Constant-only changes are common (`mov #75`→`#76`,
  struct offsets 24→20, enum bounds 12→11).
- **OBSERVED (pipeline controls):** with anchors shifted by one US record and
  no `+global` fallback, same code drops from 360 to 73 (TWIN 69, of which 49
  `anchor` — rows whose neighbour is also a twin) and `UNPAIRED` rises from
  344 to 1023; with shuffled anchors and no fallback, same code is 1. With the
  fallback on, shifted anchors give 158 and shuffled anchors 342 (TWIN 201
  and PHANTOM-SLOT 141, nearly all via `gap+global`). So the anchors drive
  the `IMMEDIATE`/`EDIT`/`REWRITE` pairings, while the same-code classes are
  recovered by similarity alone once the fallback runs: their *class* does
  not depend on the anchor, but which US twin a `TWIN` row names does.
- **OBSERVED:** the population cross-check gives a lower same-code share
  (`360/1259`, 28.6 %) than the sample (40 %); `TWIN` is `219` (17.4 %) vs
  13/40 in the sample (the sample hit the `0x003c…` cluster of twins).
  `REWRITE` (317) and `UNPAIRED` (344) are larger there; 300 of the 344
  `UNPAIRED` come from `gap` rows, and a `gap` best-of-N pick inflates
  similarity (the classifier control puts 3/40 wrong neighbours at EDIT or
  REWRITE), so the population `REWRITE` count is an upper bound on rewrites
  that have a counterpart.
- **HYPOTHESIS:** the `UNPAIRED` rows are EU-only code (they cluster in
  NOMATCH runs, consistent with whole objects absent from the US link), not
  matcher misses; nothing in this record tests what they do.
- **UNKNOWN:** whether the `IMMEDIATE`/`EDIT` constant changes touch a reader
  the map work needs; this record classifies, it does not map readers.

## Conclusion

The 1,259 are **mostly real code differences** (sample 24/40, population
899/1259 = 71.4 % including the unpaired), so most of the US code really
differs or is missing; but the **largest single class in the sample is a
matcher class**, `TWIN` (13/40), and with `PHANTOM-SLOT` (3/40) about a
third of the NOMATCH are identical code that `fn_match` cannot see. Both
are cheap: H113 (forward-pass pool slots, 141 functions in the population)
and H114 (address-order anchor for multi-twin streams, 219 TWIN rows, 188 of
them anchor-exact; it must be one-to-one and pass a shifted-anchor control). `fn_match.py` is not changed here (task Stop/Scope).
Claims C-4120–C-4126.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/nomatch_census.py archive/head256.img archive/us256.img --seed 89 --size 40 | grep '^# classes'
# classes: TWIN 13  PHANTOM-SLOT 3  POOL-LAYOUT 0  REGALLOC 0  IMMEDIATE 4  OPERANDS 0  REORDER 0  EDIT 7  REWRITE 5  UNPAIRED 8
python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all | grep '^# same code'
# same code (TWIN+PHANTOM-SLOT+POOL-LAYOUT): 360  operand-only (REGALLOC+IMMEDIATE+OPERANDS): 81  instruction changes (REORDER+EDIT+REWRITE): 474  unpaired: 344  of 1259
python3 tools/nomatch_census.py --selftest
# nomatch_census selftest: OK (20 checks, 0 failed)
```

## Follow-ups

- [ ] H113 — `fn_match`: derive pool slots with a forward pass (PHANTOM-SLOT).
- [ ] H114 — `fn_match`: pair a multi-twin masked stream by address order (TWIN).

## Corrections after navigator review

Round 1 (REQUEST CHANGES), all applied in the commit after `af5cd10`:

1. **Claim-block collision.** H114's block C-5580–C-5589 is M9.51's on
   `main`; H114 now uses C-5700–C-5709 (H113 keeps C-5570–C-5579).
2. **Merge with `main`.** `origin/main` merged (no rebase); `TODO.md` keeps
   H89 `[x]`/done, `claims.md` keeps the whole H89 section and main's
   trailing M9.51…M6.18 sections; the ledger diff against `main` is
   additions only.
3. **"Never in register allocation" was wrong** (C-4124, Interpretation):
   EU `0x00416d40`, `0x0038e284`, `0x004e3658` change registers together
   with other edits. Reworded to "no function differs *only* in register
   allocation or *only* in order".
4. **C-4121 overclaimed.** Its negative control runs `classify_bodies`
   against US record `j+1`, which controls the classifier, not the pairing;
   "body equal in 40" is true by construction for `UNIQUE`. Reworded to
   anchor control + classifier control, the body-equal count dropped (the
   tool no longer prints it), and the whole-pipeline controls added as
   `--anchor-shift`/`--anchor-shuffle` with their numbers in Observations
   (the navigator's scratch `negctl.py` gave the same numbers, except
   POOL-LAYOUT which item 7 reclassifies as TWIN).
5. **H114 Done when** gains a ±1 shifted-anchor control and a one-to-one
   requirement (30 US records are named by more than one row); "without
   guessing" became "by address order".
6. This section.
7. **The `+global` path skipped the `TWIN` test**, so 4 population rows
   were `POOL-LAYOUT` instead of `TWIN`; fixed in `classify_one`: population
   now `TWIN 219`, `POOL-LAYOUT 0` (sample unchanged).
8. Claim evidence cells now carry full commands and name the US256 head.
9. TWIN in the sample is "10 anchor, 3 gap", not all anchored; PHANTOM-SLOT's
   141/141 agreement is "address-order pairing (131 anchor, 10 gap/global)".
10. The PHANTOM-SLOT observation's verbless sentence is rewritten.
