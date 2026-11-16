# EXP-2026-11-16-H52: apply the `fn` citation audit — every `INSIDE` against `.pdata`

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `archive/head256.img`, SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (256 MiB firmware head; builds A `0x200200`, B `0x3e00200`, C `0x5200200`)
- **Tools:** `python3 3.15.0`; repo `tools/fn_audit.py` (M1.25/M1.29),
  `tools/pdata.py`, `tools/sh4xref.py` (new `--label-audit`),
  `tools/chunk_decoder_l3.py`, `tools/point_walk_l3.py`,
  `tools/l3_harness/runner.py`, `tools/selftest.py`, `tools/claims_check.py`,
  `tools/todo_check.py`. No vendor bytes are stored in the repo.
- **Claims:** C-3490–C-3499
- **Supersedes:** none (applies EXP-2026-11-15-M1.25-fn-audit / M1.29)
- **Superseded by:** none

## Question

Does every VA the scoped corpus labels `fn`/`sub_`/entry name a `.pdata`
function start, and when it does not, can each `INSIDE` be replaced by its true
start without changing what any L3 tool computes?

## Hypothesis

M1.25 found 12 unique mid-function VAs and M1.29 resolved three of them as
documented corrections. The remaining live `INSIDE` set should be exactly the
`--fix-list` rows plus instruction addresses whose line also carries the word
`fn`; applying each row (docs, `targets.json`, the `_l3.py` constants, open
`TODO.md` blocks) should leave `INSIDE 0` / exit 0, and every tool whose
constant changes must still reproduce its current output.

**Falsifier:** any `INSIDE` citation still in the scoped corpus; a `--fix-list`
row with no citation; a changed tool output after a constant fix; an `INSIDE`
VA whose true start is not reproducible by `pdata.locate`; or a `GAP` treated
as a function without a direct `bsr`/`jsr`/pool caller.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (builds A/B/C of one card image) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Offset(s) / VA(s) | pre-fix `INSIDE`: `0x003715a0`, `0x0040e4b2`, `0x00412bee`, `0x0041c7e8`, `0x0041c802`, `0x004e90c8`, `0x004ea402`, `0x005423e8`, `0x0054369e`; positive control `0x0041c7dc` (START); negative control `0x003f5194` (GAP leaf) |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/fn_audit.py` (corpus + verdicts), `tools/pdata.py` (records), `tools/sh4xref.py` (`--to`, `--label-audit`) |

## Method

1. **Sample and hash.** `archive/head256.img`, first 256 MiB, SHA-256 above;
   builds selected by CE image start, not a fitted delta.
2. **Commands.** Run from the repo root (before the fix, then after):

   ```bash
   sha256sum archive/head256.img
   python3 tools/fn_audit.py --selftest
   python3 tools/fn_audit.py archive/head256.img --fix-list
   python3 tools/fn_audit.py archive/head256.img
   python3 tools/pdata.py fn archive/head256.img --module Navi.exe \
       0x003715a0 0x0040e4b2 0x00412bee 0x0041c7e8 0x0041c802 0x004e90c8 \
       0x004ea402 0x005423e8 0x0054369e 0x00542256 0x003f5fc2 0x00413af4
   python3 tools/sh4xref.py archive/head256.img Navi.exe \
       --image-start 0x200200 --to 0x003f5194
   python3 tools/sh4xref.py archive/head256.img Navi.exe \
       --image-start 0x200200 --label-audit --sample 200 --seed 52
   python3 tools/point_walk_l3.py consts archive/head256.img
   python3 tools/chunk_decoder_l3.py --selftest
   P=/home/marek/projekty/leafre-work/m5.13
   python3 tools/chunk_decoder_l3.py run archive/head256.img \
       --cmp $P/factory/REFER001/POINT010.DAT.cmp \
       --ind $P/factory/REFER001/POINT010.DAT.ind --sec1 zero-mask
   python3 tools/l3_harness/runner.py run cmp_ind_reader --image archive/head256.img \
       --cmp $P/factory/REFER001/POINT010.DAT.cmp \
       --ind $P/factory/REFER001/POINT010.DAT.ind
   python3 tools/selftest.py
   python3 tools/claims_check.py
   python3 tools/todo_check.py
   ```

   `--label-audit` is new in this PR: it samples two-byte-aligned `Navi.exe`
   sec0 code sites with `random.Random(seed)` (default 52), keeps sites for
   which `pdata.locate` finds a record, and compares `sh4xref.function_start`
   with the record's start. It prints no vendor bytes.
3. **Controls.** *Positive:* `0x0041c7dc` is a `.pdata` START and the heuristic
   also returns it (`--label-audit` control). *Negative:* `0x003f5194` is a
   `GAP`; `sh4xref --to 0x003f5194` shows a direct `jsr` from `fn 0x003f5cdc`
   (pool `0x003f5d84`, `jsr 0x003f5d5c`), which is what makes it `GAP(leaf)`
   rather than data. `fn_audit --selftest` carries a START/INSIDE/GAP fixture.
   *Tool control:* `chunk_decoder_l3.py` was run before and after the
   `FN_CHUNK` change; `--mutate corrupt-ind` and `--mutate swap-4-8` are the
   negative controls for that output.
4. **Scope.** `tools/fn_audit.py --scope docs` scans 17 files (`TODO.md`, 13
   `docs/format/*.md`, `tools/l3_harness/targets.json`, `tools/chunk_decoder_l3.py`,
   `tools/point_walk_l3.py`). Append-only EXPs, the frozen
   `docs/research/todo-history-*.md` and closed task blocks are out of scope;
   `docs/research/reader-coverage.md` and `tools/README.md` are outside the
   glob and were corrected by hand (reported by `grep`, not by `fn_audit`).
   The corpus is 315 citations / 112 unique VAs after the fix (300 / 112
   before).
5. **Falsifier.** Stated in the Hypothesis section above.

## Observations

Before the fix (`python3 tools/fn_audit.py archive/head256.img`): exit 1,
`17 file(s) scanned, 300 citation(s), 112 unique VA(s)`,
`START 190, INSIDE 33, CORRECTED 16, GAP 29 (leaf 29), AMBIGUOUS 0, UNMAPPED 32`;
`--fix-list` printed 9 lines (M1.29 already dropped the three correction-only
VAs). The 33 `INSIDE` citations cover 9 unique VAs. Every row, with its class,
its true start and the file the fix landed in (33 rows; duplicates are the same
VA cited twice on one line):

| cited VA | where | true start | corrected in |
| --- | --- | --- | --- |
| `0x0041c7e8` | `TODO.md:518` | `0x0041c7dc` | `TODO.md` |
| `0x00412bee` | `TODO.md:518` | `0x00412ac0` | `TODO.md` |
| `0x00412bee` | `TODO.md:518` | `0x00412ac0` | `TODO.md` |
| `0x0040e4b2` | `TODO.md:518` | `0x0040e28c` | `TODO.md` |
| `0x0041c7e8` | `TODO.md:774` | `0x0041c7dc` | `TODO.md` |
| `0x00412bee` | `TODO.md:774` | `0x00412ac0` | `TODO.md` |
| `0x0041c7e8` | `TODO.md:830` | `0x0041c7dc` | `TODO.md` |
| `0x00412bee` | `TODO.md:1341` | `0x00412ac0` | `TODO.md` |
| `0x00412bee` | `TODO.md:1342` | `0x00412ac0` | `TODO.md` |
| `0x00412bee` | `TODO.md:1350` | `0x00412ac0` | `TODO.md` |
| `0x0040e4b2` | `TODO.md:1351` | `0x0040e28c` | `TODO.md` |
| `0x00412bee` | `TODO.md:1351` | `0x00412ac0` | `TODO.md` |
| `0x0041c7e8` | `TODO.md:2693` | `0x0041c7dc` | `TODO.md` |
| `0x0041c7e8` | `TODO.md:2700` | `0x0041c7dc` | `TODO.md` |
| `0x0041c7e8` | `docs/format/cmp-ind.md:179` | `0x0041c7dc` | `docs/format/cmp-ind.md` |
| `0x0041c7e8` | `docs/format/cmp-ind.md:193` | `0x0041c7dc` | `docs/format/cmp-ind.md` |
| `0x0041c7e8` | `docs/format/cmp-ind.md:195` | `0x0041c7dc` | `docs/format/cmp-ind.md` |
| `0x0041c7e8` | `docs/format/firmware.md:228` | `0x0041c7dc` | `docs/format/firmware.md` |
| `0x003715a0` | `docs/format/firmware.md:245` | `0x00371594` | `docs/format/firmware.md` |
| `0x0040e4b2` | `docs/format/firmware.md:312` | `0x0040e28c` | `docs/format/firmware.md` |
| `0x00412bee` | `docs/format/firmware.md:314` | `0x00412ac0` | `docs/format/firmware.md` |
| `0x004e90c8` | `docs/format/firmware.md:567` | `0x004e8f38` | `docs/format/firmware.md` |
| `0x004ea402` | `docs/format/firmware.md:568` | `0x004ea288` | `docs/format/firmware.md` |
| `0x0041c7e8` | `tools/l3_harness/targets.json:cmp_ind_reader` | `0x0041c7dc` | `tools/l3_harness/targets.json` |
| `0x0041c7e8` | `tools/chunk_decoder_l3.py:2` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |
| `0x0041c7e8` | `tools/chunk_decoder_l3.py:4` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |
| `0x0041c802` | `tools/chunk_decoder_l3.py:13` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |
| `0x005423e8` | `tools/chunk_decoder_l3.py:24` | `0x0054233c` | `tools/chunk_decoder_l3.py` |
| `0x0041c7e8` | `tools/chunk_decoder_l3.py:69` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |
| `0x0054369e` | `tools/chunk_decoder_l3.py:91` | `0x0054331c` | `tools/chunk_decoder_l3.py` |
| `0x0041c7e8` | `tools/chunk_decoder_l3.py:158` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |
| `0x0054369e` | `tools/chunk_decoder_l3.py:202` | `0x0054331c` | `tools/chunk_decoder_l3.py` |
| `0x0041c7e8` | `tools/chunk_decoder_l3.py:439` | `0x0041c7dc` | `tools/chunk_decoder_l3.py` |

Three citations on `TODO.md:518` and one on `TODO.md:1351` name a VA the
record's own line already pairs with the corrected start; they are the
`CORRECTED` class and were left as historical co-citations (the wrong VA stays
visible next to its correction). The instruction-site VAs `0x0041c802`,
`0x005423e8`, `0x0054369e` are calls *inside* the cited functions; their
docstrings now name the containing start and keep the instruction address as
the hook site, so `fn_audit` classifies them `INSIDE` only when the containing
start is absent from the same line.

## Interpretation

1. **The failure is real and is not a search artefact.** 9 of 112 unique cited
   VAs (8.0 %) pointed into the middle of a function while the sentence around
   them called them a function start. A reader following the citation would
   land mid-prologue; the true entry is 12–353 bytes earlier (`0x0041c7dc` vs
   `0x0041c7e8` = 12 B; `0x0054331c` vs `0x0054369e` = 898 B). This is the
   same class of error AGENTS.md warns about: an address copied from an
   instruction or a call target instead of from `.pdata`.

2. **The heuristic's mismatch rate bounds how much of the corpus can be
   trusted by eye.** `--label-audit --sample 200 --seed 52` finds 36.5 % of
   sampled `fn 0x…` labels disagree with the `.pdata` entry (36.7 % for
   mid-function sites). That is a *labeling* disagreement, not 36.5 % wrong
   addresses: many labels are deliberate instruction sites or aliases. The
   `fn_audit` scan is the authoritative count because it resolves each cited
   VA through `.pdata`, whereas `--label-audit` measures the text around it.

3. **The corrected constants do not change tool output.** `chunk_decoder_l3`
   decodes the same 42848-byte page with `r0=42848`, 1057251 instructions and
   memcpy=11 before and after `FN_CHUNK 0x0041c7e8 → 0x0041c7dc`,
   `DST_SLOT 40 → 16`; the corrupt-ind and swap-4-8 mutation controls still
   give `r0=-1` and `r0=65536`. Reverting to the old entry *and* the old
   `DST_SLOT` also reproduces the page, so the fix is an ABI correction (the
   documented `sp+72` at `0x0041c802` is `sp+16` from the true frame), not an
   output change.

4. **One entry-VA change was rejected.** `point_walk_l3.py` cites `0x003f51ae`
   as the `0x3ff`/`0xfc00` mask anchor. That byte pattern is an instruction
   inside leaf `0x003f5194`, not a `.pdata` start (`GAP(leaf)`); moving the
   label to `0x003f51b8` makes the tool's own self-check report `anchor … in
   0x3ff list: False`, so the constant stays and the docstring says it is an
   instruction anchor. This is the AGENTS.md rule applied: change a constant
   only if the tool still reproduces its output.

## Conclusion

H52's `Done when` passes. `fn_audit` over 17 files and 315 citations reports
`START 229, INSIDE 0, CORRECTED 25, GAP 29 (leaf 29), AMBIGUOUS 0, UNMAPPED
32` and exits 0 with an empty `--fix-list`; before the fix it was `START 190,
INSIDE 33, CORRECTED 16, GAP 29` and exit 1. All 9 `INSIDE` unique VAs have a
tool re-run or a reader-coverage row showing the corrected start, and each
correction has a claim row (C-3490–C-3497). The remaining `GAP` and `UNMAPPED`
rows are leaf/indirect targets and out-of-build VAs, not mislabelled starts;
they are listed with fixing tasks in `docs/research/fn-audit-2026-11-16.md`.

## Reproduction

```bash
python3 tools/fn_audit.py archive/head256.img                      # exit 0, INSIDE 0
python3 tools/fn_audit.py archive/head256.img --fix-list            # empty
python3 tools/sh4xref.py archive/head256.img Navi.exe \
    --label-audit --sample 200 --seed 52                           # 36.5 % / 36.7 %
python3 tools/chunk_decoder_l3.py --selftest                       # PASS
python3 tools/fn_audit.py --selftest && python3 tools/sh4xref.py --selftest
python3 tools/selftest.py                                          # 88 passed, 0 failed
python3 tools/claims_check.py && python3 tools/todo_check.py       # OK
```

Inputs: `archive/head256.img` (256 MiB head of the EU 2011 image, SHA-256
`92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`), the
`REFER001/POINT010.DAT.{cmp,ind}` pair from the factory tree for the decoder
run.

## Follow-ups

- Resolve the 29 `GAP(leaf)` citations against a caller map (`sh4xref
  --calls`) before any of them is promoted to a reader VA; task ids in
  `docs/research/fn-audit-2026-11-16.md`.
- The 32 `UNMAPPED` VAs (MapUpdate.exe/gwes.exe/AppLaunch.dll addresses in a
  Navi.exe image) need a per-module image head; not an H52 defect.
- Re-run `fn_audit` after every reader claim so a copied instruction address
  cannot re-enter a `fn 0x…` label.
