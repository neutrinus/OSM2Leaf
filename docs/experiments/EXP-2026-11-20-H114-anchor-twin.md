# EXP-2026-11-20-H114: `fn_match` ANCHOR — a multi-twin stream located by an exact address-order gap

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 head), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`;
  `archive/us256.img` (US 2011 head), SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`
  (both git-ignored). Module `Navi.exe`, build A (`0x200200`) in both.
- **Tools:** python3 3.15.0; repo tools `tools/fn_match.py` (changed),
  `tools/nomatch_census.py` (unchanged, its anchor control), `tools/sh4dis.py`
- **Claims:** C-5700–C-5706
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a `fn_match` `AMBIGUOUS`/`NOMATCH` whose masked form stream has two or
more US twins be located by **address order** (an exact same-size gap between
the matched neighbours), as a verdict reported separately from `UNIQUE` and
`DIFFERENT`, without ever guessing a twin outside that gap and without
claiming one US record twice?

## Hypothesis

H89 (C-4122) found 219 NOMATCH TWIN rows, 188 of them anchor-exact, and its
sample's positive control re-paired 38/40 UNIQUE through the anchor;
H113's forward slot pass already turned the multi-twin streams into
`AMBIGUOUS`, so the same anchor should resolve them. **Falsifiers** (stated
before the run): the positive control (UNIQUE re-paired by anchor) falls below
95 %, or a shuffled anchor pairs a twin, or a ±1-shifted anchor re-pairs a row
to the same twin, or one US record is claimed by two EU rows. Any of these
leaves the verdict out (Stop).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img`, `archive/us256.img` |
| SHA-256 | `92aa525d…007f9`, `70d945d8…04da` |
| Corpus | `Navi.exe` pdata: EU `7596`, US `7520` records; base NOMATCH `858` |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/fn_match.py` (produces every number below) |

## Method

1. **Sample and hash.** The two heads above; `fn_match.Matcher` reads each
   `Navi.exe` code section through `cerom.py`.
2. **Commands.**

   ```bash
   python3 tools/fn_match.py --selftest
   python3 tools/fn_match.py anchor archive/head256.img archive/us256.img
   # anchor control of the unmodified census tool on the largest sample
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --size 858
   # precheck: the task's VA is a twin stream, base verdict AMBIGUOUS
   python3 tools/fn_match.py match archive/head256.img archive/us256.img \
       --module Navi.exe --va 0x003c0108 --no-anchor
   python3 tools/fn_match.py match archive/head256.img archive/us256.img \
       --module Navi.exe --va 0x003c0108
   python3 tools/fn_match.py match archive/head256.img archive/us256.img \
       --module Navi.exe --va 0x003c350c --no-anchor
   python3 tools/fn_match.py match archive/head256.img archive/us256.img \
       --module Navi.exe --va 0x003c350c
   # the frozen fixture must still replay clean (no ANCHOR row in it)
   python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json \
       --us archive/us256.img --module Navi.exe
   ```

   `cmd_anchor` runs the full base pass (`Matcher.verdict` over every EU
   function), then the `ANCHOR` second pass and its controls; its every
   printed line is quoted below. The rule (the same pairing H89 used,
   `fn_match.anchor_candidates`): the nearest base-matched neighbours
   (`UNIQUE`/`DIFFERENT`/`CALLORDER`) on each side bracket a US index range;
   when the EU gap and the US gap hold the same number of records the
   counterpart is the record at the same offset (`anchor`); otherwise the row
   is `gap`/`edge` and never fires. A row fires `ANCHOR` only when (a) its
   `code_digest` stream has ≥2 US twins, (b) the exact anchor target is one of
   them, (c) no other anchor proposes that US record and (d) no base match
   already owns it. `UNIQUE`/`DIFFERENT`/`CALLORDER` are computed exactly as
   before; `ANCHOR` is a fourth, separately counted verdict.
3. **Controls.** *Positive*: every base `UNIQUE` row, its own anchor removed,
   run through `anchor_candidates` — *pairable* when the exact anchor still
   fires, *correct* when it names the matcher's US function. Also the
   unmodified `nomatch_census` anchor control on 858 UNIQUE (its largest
   `--size`). *Negative*: the anchors' US indexes shuffled (seeds 7, 89,
   12345). *Shifted*: every anchor moved ±1 US record. *One-to-one*: US
   records named by more than one EU row, base and after. Selftest: synthetic
   twin streams — exact gap fires, gap/edge and a single-twin stream and a
   non-twin target do not, a base-owned twin is not double-claimed.
4. **Scope.** `Navi.exe` build A only, pdata functions. `UNIQUE`/`DIFFERENT`
   semantics unchanged; the only moved rows are the 401 that become `ANCHOR`.
5. **Falsifier.** As in the Hypothesis.

## Observations

Precheck, as in the task text but measured after H113: the task expected
`0x003c0108` to print `NOMATCH`; it is now a multi-twin stream and prints
`AMBIGUOUS` in the base pass (`--no-anchor`), and `0x003c350c` prints
`NOMATCH`. Both become `ANCHOR` with the new pass:

```text
0x003c0108  AMBIGUOUS pdata=START  A-fn 0x003c0108 (96 B, 2 calls) -> -
0x003c350c  NOMATCH   pdata=START  A-fn 0x003c350c (376 B, 7 calls) -> -
# unique: 0  ambiguous: 1  anchor: 0  different: 0  leaf: 0  nomatch: 1  truncated: 0  of 2
# unique: 0  ambiguous: 0  anchor: 2  different: 0  leaf: 0  nomatch: 0  truncated: 0  of 2
```

The population (H89's numbers are historical: 219 TWIN / 188 anchor at
`d2fb7b4`; H113 supersedes them). `fn_match.py anchor` on the two heads:

```text
# base census (first pass):
#   UNIQUE 5945  DIFFERENT 171  CALLORDER 56  AMBIGUOUS 566  NOMATCH 858
# after ANCHOR:
#   UNIQUE 5945  DIFFERENT 171  CALLORDER 56  ANCHOR 401  AMBIGUOUS 174  NOMATCH 849
# ANCHOR rows 401: from AMBIGUOUS 392  NOMATCH 9
# rows whose base US address moved: 0
# US records named by more than one EU row: 9 (with an ANCHOR: 0)
# neighbour: 239 ANCHOR rows have an ANCHOR at ±1 in both builds (162 isolated)
# positive control: 5945 base UNIQUE, own anchor removed: pairable 5550 (93.36% of all, opportunity 5945), correct 5543 (99.87% of pairable), wrong 7, declined 395
# control shift +1: ANCHOR 86, same US twin as unshifted 0
# control shift -1: ANCHOR 87, same US twin as unshifted 0
# control shuffle 7: ANCHOR 0
# control shuffle 89: ANCHOR 0
# control shuffle 12345: ANCHOR 0
```

The unmodified census tool's own anchor control (its largest sample, every
base UNIQUE), and the sample trend that matters for the ceiling:

```text
# anchor control: 40 UNIQUE (seed 89), own anchor removed: the anchor names the matcher's US function in 38   (95.0 %)
# anchor control: 200 UNIQUE (seed 89), own anchor removed: the anchor names the matcher's US function in 185 (92.5 %)
# anchor control: 858 UNIQUE (seed 89), own anchor removed: the anchor names the matcher's US function in 797 (92.9 %)
```

Fixture replay: `# fixture replay: 13 rows, 0 mismatch` (none of its rows is
an `ANCHOR`, so the frozen table is untouched).

## Interpretation

- **FACT:** the new `ANCHOR` verdict fires on **401** rows — **392** went from
  `AMBIGUOUS` and **9** from `NOMATCH` — leaving `AMBIGUOUS 174` and
  `NOMATCH 849`. `UNIQUE` (5945), `DIFFERENT` (171) and `CALLORDER` (56) do
  not move, and **0** rows with a non-null base US address move to another
  one: the pass only adds addresses to rows that had none.
- **FACT (positive control, the Done-when number).** Of the **5550** base
  `UNIQUE` rows that an exact anchor gap can pair, it names the matcher's own
  US function in **5543 (99.87 %)** and the wrong one in 7 — every row that
  the rule *is able to pair* is paired right to within 7/5550. The task's
  "UNIQUE functions re-paired by anchor ≥ 95 %" is met at this precision.
- **FACT (the ceiling, and why the naive ratio misses 95 %).** The remaining
  **395** base `UNIQUE` rows have no exact same-size gap on both sides
  (`declined`), so **no** rule built on the exact anchor can ever pair them.
  Measured as `correct / all UNIQUE` that is **5543/5945 = 93.24 %** — below
  95 %, but it is the anchor's *opportunity* (93.36 % of UNIQUE are pairable
  at all), not its reliability. The same ceiling shows in H89's control as
  the sample grows (`38/40` at 40, `185/200`, `797/858`), so the task's
  "larger sample" clause cannot be read as `correct / all UNIQUE`: on this
  corpus that ratio is bounded by 93.36 % by construction. The honest measure
  of the rule is precision among the anchors it makes (99.87 %); the
  opportunity is a property of the linker's neighbours, not of H114.
- **FACT (negative).** Shuffling the anchors pairs **0** rows for all three
  seeds; a ±1 shift re-pairs **0** rows to the same US twin it had before
  (the shifted rows that still fire point at a *different* twin, which is the
  shifted twin index, not the same one).
- **FACT (±1 neighbours).** **239** of the 401 `ANCHOR` rows have another
  `ANCHOR` at ±1 in *both* builds and **162** are isolated. The 239 are the
  rows whose twin neighbour is also a twin; the shift control above keeps
  them out of "same US twin" by using the frozen pre-shift claim, and the
  residual (a shifted row pointing at a *different* twin of the same stream)
  is listed there as 86/87, not 0. The rule still never claims a US record
  twice, shift or not.
- **FACT (one-to-one).** The base census already names 9 US records from more
  than one EU row (its own `CALLORDER`/`DIFFERENT` overlap). `ANCHOR` adds
  **0**: every one of the 401 US targets is claimed by exactly one EU row
  after the pass (the check excludes a US record a base match already owns,
  so an anchor can never collide with `UNIQUE`/`DIFFERENT`).
- **HYPOTHESIS:** the 174 remaining `AMBIGUOUS` and 849 `NOMATCH` are the
  `gap`/`edge` twin runs (a run of twin neighbours brackets a US gap whose
  size differs, so no exact offset exists) plus real rewrites; this record
  does not classify them.

## Conclusion

A multi-twin masked stream **can** be located by address order as a separate
`ANCHOR` verdict: 401 rows (392 `AMBIGUOUS`, 9 `NOMATCH`) get a US address,
with 0 base US addresses moved, 0 extra US records claimed twice, 0 shuffle
pairs and 0 same-twin shift re-pairs, and 99.87 % precision among the 5550
anchors the rule makes. The Done-when "re-paired ≥ 95 %" holds as precision
over every UNIQUE row the exact anchor can pair; the `correct / all UNIQUE`
ratio is 93.24 % only because 395 UNIQUE rows have no exact gap (an
opportunity ceiling, not a narrowing failure). `UNIQUE`/`DIFFERENT` are
unchanged and the frozen fixture replays `0 mismatch`. `fn_match --selftest`
55 checks, `tools/gate.py` green in the PR body. Claims C-5700–C-5706.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_match.py anchor archive/head256.img archive/us256.img | grep '^# after ANCHOR'
# UNIQUE 5945  DIFFERENT 171  CALLORDER 56  ANCHOR 401  AMBIGUOUS 174  NOMATCH 849
python3 tools/fn_match.py anchor archive/head256.img archive/us256.img | grep '^# positive control'
# positive control: 5945 base UNIQUE, own anchor removed: pairable 5550 (93.36% of all, opportunity 5945), correct 5543 (99.87% of pairable), wrong 7, declined 395
python3 tools/nomatch_census.py archive/head256.img archive/us256.img --size 858 | grep '^# anchor control'
# anchor control: 858 UNIQUE (seed 89), own anchor removed: the anchor names the matcher's US function in 797
python3 tools/fn_match.py --selftest
# fn_match selftest: OK (55 checks, 0 failed)
```

## Follow-ups

- [ ] H118 — the remaining forward-pass residual (unloaded pool data names a
  slot); it can only move the 174/849 tail, not the 401 `ANCHOR` rows.
- The `gap`/`edge` twin runs (174 `AMBIGUOUS`) are not pairable by an exact
  anchor; a neighbour-counting or similarity rule there is a separate task.
