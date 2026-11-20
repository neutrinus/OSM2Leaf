# EXP-2026-11-20-H63: `CORRECTED` names its evidence (`line` vs `pin`)

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 firmware head, IMG256; the first 268,435,456 B of the EU card), SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`. Corpora: the `b56fed2` docs tree (frozen, M1.29 merge) and the live docs tree of this branch after merging `origin/main` at `1e904c2`.
- **Tools:** `python3 3.13.18`; `tools/fn_audit.py` (this branch: `Verdict.evidence`, `CORRECTED(line|pin)` label, `fn_audit: CORRECTED <n> (<line> line, <pin> pin)` summary line, `--drop-pin`), `tools/pdata.py fn`, `tools/sh4dis.py`
- **Claims:** C-3830–C-3836 (C-3837–C-3839 reserved)
- **Supersedes:** none
- **Superseded by:** none

## Question

For each `CORRECTED` citation, did this occurrence carry its own arrow pair to the true start (`line`) or did the static `CORRECTION_ONLY` allowlist resolve it (`pin`), and how many of each are there on the frozen `b56fed2` corpus and on the live tree?

## Hypothesis

`_resolved` has exactly two branches, and they are mutually exclusive: a `ctx` citation that carries its own pair is decided by the pair alone, and the pin is consulted only when this occurrence carries no arrow pair of its own (the line may still name the start in another form). So the 13 `CORRECTED` rows of `b56fed2` split into `line + pin = 13` with no row counted twice, and the `INSIDE 33` count stays the same. M1.29's composition table, `0x00542256` ×6, `0x00413af4` ×3, `0x003f5fc2` ×2, `0x0041c7e8` ×1 and `0x00412bee` ×1, predicts that the two live-elsewhere VAs are `line`, because they are not pinned. The three pinned VAs can be either.

**Falsifier:** any of these refutes it:
- on `b56fed2`, the H63 tool prints a total other than `CORRECTED 13`, or `INSIDE` other than 33;
- `line + pin ≠ 13`;
- `--drop-pin 0x00542256` gives anything other than `INSIDE 36, CORRECTED 10`;
- a pinned VA has an `INSIDE` row whose own line pairs a different start. That is the second defect named in the task, and it must then be listed.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (IMG256, EU 2011 head) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| VA(s) | pins `0x00542256`, `0x003f5fc2`, `0x00413af4`; line-resolved `0x0041c7e8`, `0x00412bee`, `0x0040e4b2` |
| Corpus A | detached worktree at `b56fed2` (17 docs files for its own collector; 18 for the current collector, which adds `tools/build_targets.py`) |
| Corpus B | this branch after `git merge origin/main` (`1e904c2`), 24 docs files |
| Repo tool | `tools/fn_audit.py` |

## Method

1. **Sample and hash.** `sha256sum archive/head256.img` gives `92aa525d…a007f9`, which is the hash above.
2. **Commands.** The b56fed2 corpus is scanned by copying this branch's `fn_audit.py` and its three imports over the detached tree. `REPO` is the tool's parent directory, so the docs read are b56fed2's. The copy is then reverted.

   ```bash
   H=/home/user/OSM2Leaf.task-h63-corrected-evidence     # this branch
   IMG=$H/archive/head256.img
   W=$HOME/scratch/h63/wt
   git -C $H worktree add --detach $W b56fed2
   cd $W
   python3 tools/fn_audit.py $IMG --scope docs --quiet          # b56fed2's own tool (baseline)
   cp $H/tools/{fn_audit,pdata,cerom,build_targets}.py tools/
   python3 tools/fn_audit.py $IMG --scope docs --quiet          # H63 tool, b56fed2 docs
   python3 tools/fn_audit.py $IMG --scope docs | grep 'CORRECTED('
   python3 tools/fn_audit.py $IMG --scope docs --quiet --drop-pin 0x00542256
   python3 tools/fn_audit.py $IMG --scope docs --quiet \
       --drop-pin 0x00542256 --drop-pin 0x003f5fc2 --drop-pin 0x00413af4
   python3 tools/fn_audit.py $IMG --scope docs | grep -E '^0x(003f5fc2|00413af4|00542256) .*INSIDE'
   git checkout -- tools && rm -f tools/build_targets.py
   cd $H                                                        # live tree
   python3 tools/fn_audit.py $IMG --scope docs | grep -E 'CORRECTED|^fn_audit'
   python3 tools/fn_audit.py $IMG --scope docs --quiet --drop-pin 0x00542256
   python3 tools/fn_audit.py $IMG --scope docs --quiet \
       --drop-pin 0x00542256 --drop-pin 0x003f5fc2 --drop-pin 0x00413af4
   python3 tools/fn_audit.py $IMG --scope docs | grep -E '^0x(003f5fc2|00413af4|00542256) .*INSIDE'
   python3 tools/fn_audit.py $IMG --corpus docs/research/fn-audit-corpus-2026-11-16.json \
       --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json | grep -E '^fn_audit: (CORRECTED|START)'
   python3 tools/pdata.py fn --module Navi.exe $IMG 0x00542256 0x003f5fc2 0x00413af4
   python3 tools/sh4dis.py --va 0x00542250 --count 4 $IMG Navi.exe
   python3 tools/sh4dis.py --va 0x00413af4 --count 1 $IMG Navi.exe
   python3 tools/sh4dis.py --va 0x003f5fc2 --count 1 $IMG Navi.exe
   python3 tools/sh4dis.py --va 0x00413a6c --count 2 $IMG Navi.exe
   python3 tools/sh4dis.py --va 0x003f5f48 --count 2 $IMG Navi.exe
   python3 tools/fn_audit.py --selftest
   python3 tools/selftest.py --only fn_audit
   ```

3. **Controls.**
   - *Positive:* in the selftest, a synthetic `ctx` citation with its own pair `0x401048 → 0x401040` must print `CORRECTED(line) 0x00401040`. The same VA, bare and allowlisted, must print `CORRECTED(pin) 0x00401040`. A mixed set must print `fn_audit: CORRECTED 2 (1 line, 1 pin)`. On the real corpus, b56fed2's own tool must reproduce the task precheck `START 190, INSIDE 33, CORRECTED 13`.
   - *Negative:* these are also in the selftest:
     - an allowlisted VA whose own line pairs a different start (`0x401100`) must stay `INSIDE`, so the pin never rescues a wrong pair;
     - a wrong pinned start must stay `INSIDE`;
     - a live `fn` label stays `INSIDE`;
     - `--fix-list` must stay `["0x00401048 -> 0x00401040"]` with a pin `CORRECTED` present;
     - `--drop-pin` of a VA that is not pinned, or combined with `--write-snapshot`, must exit 2 and leave the allowlist intact.

     On the real corpus, `--drop-pin` must move only the dropped pin's `pin` rows to `INSIDE`.
4. **Scope.** `--scope docs` only, on two corpora: b56fed2, with 18 files, 321 citations and 123 unique VAs for the current collector, and the live tree, with 24 files, 552 citations and 217 unique VAs. The corpus-mode split is also printed for the gate's two frozen snapshots. The l3 scope is not re-measured live; its frozen overlay is measured instead. Citations are not changed (that is H52), and no pin is added or removed in the code.
5. **Falsifier.** See Hypothesis, which states it before any result.

## Observations

**Baseline on `b56fed2` with its own tool** reproduces the task precheck:

```
fn_audit: 17 file(s) scanned, 297 citation(s), 112 unique VA(s)
fn_audit: START 190, INSIDE 33, CORRECTED 13, GAP 29 (leaf 29), AMBIGUOUS 0, UNMAPPED 32
```

**H63 tool on the `b56fed2` docs:**

```
fn_audit: START 195, INSIDE 33, CORRECTED 13, GAP 37 (leaf 37), AMBIGUOUS 0, UNMAPPED 43
fn_audit: CORRECTED 13 (5 line, 8 pin)
fn_audit: correction-only (no live label): 0x003f5fc2, 0x00413af4, 0x00542256
```

The current collector also scans `tools/build_targets.py`, which accounts for the 18th file. That file adds 5 `START`, 8 `GAP` and 11 `UNMAPPED`, and no `INSIDE` or `CORRECTED`. `INSIDE 33` and `CORRECTED 13` match the baseline exactly.

The 13 rows, verbatim (`grep 'CORRECTED('`):

```
0x0041c7e8  TODO.md:512   CORRECTED(line) 0x0041c7dc  Navi.exe  A
0x00412bee  TODO.md:512   CORRECTED(line) 0x00412ac0  Navi.exe  A
0x00542256  TODO.md:512   CORRECTED(line) 0x00542250  Navi.exe  A
0x003f5fc2  TODO.md:516   CORRECTED(pin) 0x003f5f48   Navi.exe  A
0x00542256  TODO.md:714   CORRECTED(pin) 0x00542250   Navi.exe  A
0x00542256  TODO.md:729   CORRECTED(line) 0x00542250  Navi.exe  A
0x00542256  TODO.md:729   CORRECTED(pin) 0x00542250   Navi.exe  A
0x00542256  TODO.md:766   CORRECTED(line) 0x00542250  Navi.exe  A
0x00413af4  TODO.md:766   CORRECTED(pin) 0x00413a6c   Navi.exe  A
0x003f5fc2  TODO.md:771   CORRECTED(pin) 0x003f5f48   Navi.exe  A
0x00413af4  TODO.md:771   CORRECTED(pin) 0x00413a6c   Navi.exe  A
0x00542256  TODO.md:771   CORRECTED(pin) 0x00542250   Navi.exe  A
0x00413af4  TODO.md:1281  CORRECTED(pin) 0x00413a6c   Navi.exe  A
```

Arithmetic against M1.29's 6+3+2+1+1 composition:

| VA | M1.29 count | line | pin |
| --- | --- | --- | --- |
| `0x00542256` | 6 | 3 (512, 729, 766) | 3 (714, 729, 771) |
| `0x00413af4` | 3 | 0 | 3 (766, 771, 1281) |
| `0x003f5fc2` | 2 | 0 | 2 (516, 771) |
| `0x0041c7e8` | 1 | 1 (512) | 0 |
| `0x00412bee` | 1 | 1 (512) | 0 |
| **total** | **13** | **5** | **8** |

The totals check: 3+0+0+1+1 = 5, 3+3+2+0+0 = 8, and 5+8 = 13.

**Effect of dropping pins on `b56fed2`:**
- With `--drop-pin 0x00542256`: `START 195, INSIDE 36, CORRECTED 10, …`, and the split line reads `fn_audit: CORRECTED 10 (5 line, 5 pin)`. That is 33+3 = 36 and 13−3 = 10: exactly the three `pin` rows of `0x00542256` (714, 729, 771) moved. Its three `line` rows stayed `CORRECTED`.
- With all three pins dropped: `INSIDE 41, CORRECTED 5`, and the split reads `fn_audit: CORRECTED 5 (5 line, 0 pin)`. That is 33+8 = 41.

**Live tree** (this branch after merging `origin/main` `1e904c2`, `--scope docs`):

```
fn_audit: 24 file(s) scanned, 552 citation(s), 217 unique VA(s)
fn_audit: START 370, INSIDE 0, CORRECTED 20, GAP 43 (leaf 43), AMBIGUOUS 0, UNMAPPED 119
fn_audit: CORRECTED 20 (12 line, 8 pin)
```

These were measured before this task added its own TODO and EXP lines. The `pin` rows are:
- `0x003f5fc2` ×2 (`TODO.md:666`, `1260`);
- `0x00542256` ×3 (`828`, `1227`, `1260`); line 828 is H63's own Goal, which names the VA bare;
- `0x00413af4` ×3 (`1255`, `1260`, `1950`).

The `line` rows are:
- `0x0041c7e8` ×3;
- `0x00412bee` ×4;
- `0x0040e4b2` ×2;
- `0x00542256` ×3.

Dropping pins on the live tree:
- `--drop-pin 0x00542256` gives `INSIDE 3, CORRECTED 17 (12 line, 5 pin)`;
- dropping all three gives `INSIDE 8, CORRECTED 12 (12 line, 0 pin)`.

The task's `26f33cd` figures (`START 229, CORRECTED 25`; popped `INSIDE 5, CORRECTED 20`) came from an earlier board, and later merges have moved them.

**Second defect.** No pinned VA has an `INSIDE` row on either corpus. Both `grep -E '^0x(003f5fc2|00413af4|00542256) .*INSIDE'` searches print nothing. So no pin-resolved VA appears with a line that pairs a different start: **0 second defects**.

**Frozen snapshots (corpus mode, the gate's input).** The docs base gives `CORRECTED 20 (12 line, 8 pin)` and the l3 overlay gives `CORRECTED 9 (2 line, 7 pin)`. Six of those 7 l3 `pin` rows sit in H63's own open block (`TODO.md:828–833`). Marking H63 done removes the block from the l3 open-block scope, and `--write-snapshot` re-freezes the overlay in the same commit. After that the overlay reads (at the PR's final merge of `origin/main`; its `START` count moves with other merges) `fn_audit: CORRECTED 3 (2 line, 1 pin)`, with `CORPUS OK: L3 OVERLAY` (re-quoted after navigator review: see below). The split is re-derived from the image, because a snapshot row stores only the class.

**Pin re-checks:**

```
$ python3 tools/pdata.py fn --module Navi.exe $IMG 0x00542256 0x003f5fc2 0x00413af4
0x00542256 INSIDE fn 0x00542250 prologue 14 B, length 0xdc, end 0x0054232c
0x003f5fc2 INSIDE fn 0x003f5f48 prologue 16 B, length 0x88, end 0x003f5fd0
0x00413af4 INSIDE fn 0x00413a6c prologue 18 B, length 0xf8, end 0x00413b64
$ python3 tools/sh4dis.py --va 0x00542250 --count 4 $IMG Navi.exe
0x00542250  2f86  mov.l r8,@-r15
0x00542252  2f96  mov.l r9,@-r15
0x00542254  2fa6  mov.l r10,@-r15
0x00542256  4f22  sts.l pr,@-r15
$ python3 tools/sh4dis.py --va 0x00413af4 --count 1 $IMG Navi.exe
0x00413af4  430b  jsr @r3
$ python3 tools/sh4dis.py --va 0x003f5fc2 --count 1 $IMG Navi.exe
0x003f5fc2  0009  nop
$ python3 tools/sh4dis.py --va 0x00413a6c --count 2 $IMG Navi.exe
0x00413a6c  2f86  mov.l r8,@-r15
0x00413a6e  2f96  mov.l r9,@-r15
$ python3 tools/sh4dis.py --va 0x003f5f48 --count 2 $IMG Navi.exe
0x003f5f48  2f86  mov.l r8,@-r15
0x003f5f4a  2f96  mov.l r9,@-r15
```

**Selftest:** `python3 tools/fn_audit.py --selftest` printed `selftest: OK (81 checks, 0 failed)` at review time (83 after the corrections below). That was 72 before H63; the 9 first-round checks are the H63 ones listed under Controls. `python3 tools/selftest.py --only fn_audit` gives `passed=1 failed=0`, and `python3 tools/gate.py` reports `4 pass, 0 fail, 0 skip`.

## Interpretation

- **FACT:** on the frozen `b56fed2` corpus, 8 of the 13 `CORRECTED` occurrences carry no arrow pair of their own and are resolved by the static allowlist; 5 are resolved by their own `VA → start` pair (C-3831). Of the 8, 2 sit on lines that name the start in another form: `TODO.md:729` has `0x00542256 → fn 0x00542250` and then a bare `0x00542256`, and `TODO.md:1281` names `fn 0x00413a6c` without an arrow. So `pin` means "no arrow pair on this occurrence", not "the line names no start" (corrected after navigator review). The split leaves `INSIDE 33` and `CORRECTED 13` unchanged, so the Stop condition does not apply.
- **FACT:** the two branches never both fire for one citation. A line that carries a pair is decided by that pair. A pinned VA with a wrong pair stays `INSIDE` (selftest), and on both real corpora no such line exists (C-3834).
- **FACT:** `--drop-pin 0x00542256` on `b56fed2` moves exactly the three `pin` rows of that VA, giving `INSIDE 36, CORRECTED 10` (C-3832). That is the task's precheck, reproduced with a committed flag instead of a hand edit.
- **OBSERVED:** the live tree's `CORRECTED 20` is not "the same `INSIDE`, plus prose", as the Done-when expected. H52 already rewrote the live `INSIDE` citations (live `INSIDE 0`), and the 7 extra `line` rows are post-H52 pairs. The `pin` count is 8 on both corpora, at different lines (C-3833).
- **OBSERVED:** each kept pin has a re-check that does not use the pin or `.pdata`: `sh4dis` shows that all three true starts open with `mov.l r8,@-r15; mov.l r9,@-r15`. The `0x00542256` check is byte-level: `0x00542250` opens with three register pushes, and `0x00542256` is the fourth prologue instruction (`sts.l pr`). The `0x00413af4` check confirms that the VA is a `jsr` call site, not an entry. M1.24's `--parent-of`, which the task names for `0x00542256`, is not on `main` yet (M1.24 is in progress), so its `Pin:` line names it as the follow-on check (C-3835).

Pin lines:

- `Pin: 0x00542256 → 0x00542250`.
  - Re-check now: `python3 tools/sh4dis.py --va 0x00542250 --count 4 IMG256 Navi.exe` shows the prologue; the push sequence puts the VA mid-prologue.
  - Also: `python3 tools/pdata.py fn --module Navi.exe IMG256 0x00542256`.
  - When M1.24 merges: `sh4literal.py --parent-of 0x00542256`.
- `Pin: 0x003f5fc2 → 0x003f5f48`. Re-check: `python3 tools/sh4dis.py --va 0x003f5f48 --count 2 IMG256 Navi.exe` (`mov.l r8,@-r15; mov.l r9,@-r15`, a prologue), `python3 tools/pdata.py fn --module Navi.exe IMG256 0x003f5fc2` (`end 0x003f5fd0`) and `python3 tools/sh4dis.py --va 0x003f5fc2 --count 1 IMG256 Navi.exe` (`nop`, an instruction in the body, not an entry).
- `Pin: 0x00413af4 → 0x00413a6c`. Re-check: `python3 tools/sh4dis.py --va 0x00413a6c --count 2 IMG256 Navi.exe` (`mov.l r8,@-r15; mov.l r9,@-r15`, a prologue), `python3 tools/pdata.py fn --module Navi.exe IMG256 0x00413af4` and `python3 tools/sh4dis.py --va 0x00413af4 --count 1 IMG256 Navi.exe` (`jsr @r3`, the call site).

## Conclusion

`fn_audit` rows now read `CORRECTED(line) 0x…` or `CORRECTED(pin) 0x…`. Live runs and `--corpus` runs print `fn_audit: CORRECTED <n> (<line> line, <pin> pin)` after the frozen two-line summary. The split is not stored in snapshots, so M1.30 snapshots stay compatible. `is_failure`, `--fix-list` and the snapshot classes are unchanged.

On `b56fed2` the split is `CORRECTED 13 (5 line, 8 pin)`. On the live tree it is `CORRECTED 20 (12 line, 8 pin)`. `--drop-pin VA` makes the pin-removal measurement a command.

All three pins are kept, each with a runnable re-check. Whether pin-resolved occurrences such as `TODO.md:714`/`828` (no start on the line) or `729`/`1281` (start named in another form) should instead carry their own arrow pair is H52's question (citations), not this task's.

## Corrections after navigator review

The PR #319 navigator review approved the numbers and the code after six fixes. Each one was applied in this PR:

1. **Merge and snapshots (HIGH).** `origin/main` was merged at `302154f`, then again at `fc97028`, which includes H77 (#316). H77 made `docs/research/fn-audit-l3-corpus-2026-11-20.json` the live l3 overlay that `gate.py` reads. So `fn-audit-l3-corpus-2026-11-16.json` is kept exactly as `main` has it (frozen by H77), and the 11-20 overlay is the one re-synced with `--scope l3 --write-snapshot`. The docs base snapshot was re-frozen too. After the refresh:
   - docs base: `START 376, INSIDE 0, CORRECTED 20`, `fn_audit: CORRECTED 20 (12 line, 8 pin)`, `CORPUS OK: DOCS BASE`;
   - l3 overlay: `fn_audit: CORRECTED 5 (3 line, 2 pin)`, `CORPUS OK: L3 OVERLAY`. The 5 rows are H51 pm-review :174 (pin), M1.25 :84 (line), M1.29 :72 (line), and this EXP's `Pin:` line, which holds one line occurrence and one pin occurrence.

   C-3836 is re-quoted, and `gate.py` reports 4 pass.
2. **Overclaim on what `pin` means (HIGH).** `pin` means that *this occurrence carries no arrow pair of its own*. It does not mean the line names no start. On `b56fed2`:
   - `TODO.md:729` pairs the third H51 VA with its start by an arrow and then names the same VA bare, so it holds one `line` and one `pin` occurrence;
   - `TODO.md:1281` names the `jsr` pin's enclosing `fn` in non-arrow form.

   This item deliberately writes no hex VA, so that it adds no rows to the l3 overlay it quotes. The exact text is in the FACT bullet above.

   The Question, the Hypothesis, the first FACT bullet, the Conclusion and C-3830/C-3831 now say: "8 occurrences carry no arrow pair of their own; 2 (729, 1281) sit on lines that name the start in another form". `_resolved` is unchanged, so no number moves.
3. **Pin re-checks independent of `.pdata` (LOW).** `sh4dis --va 0x00413a6c --count 2` and `sh4dis --va 0x003f5f48 --count 2` both print `mov.l r8,@-r15; mov.l r9,@-r15`. They were added to the Method, the Observations, the `Pin:` lines and C-3835.
4. **Selftest (LOW).** Two checks were added: a successful `--drop-pin` run, in which the pin's row is `INSIDE` during the run and the allowlist is restored afterwards, and two occurrences of one VA on one line, which give evidence `["line", "pin"]`. The selftest now reads `selftest: OK (83 checks, 0 failed)`.
5. **`--drop-pin` mutated module state (LOW).** `main` now validates every VA before touching the allowlist and drops the pins only around `_run(...)`. A `try/finally` then restores `CORRECTION_ONLY`.
6. **Setup reference (LOW).** C-3831, C-3832 and C-3834 now say "(setup: EXP §Method step 2)" for the `b56fed2` tree.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_audit.py IMG256 --scope docs --quiet          # on a b56fed2 tree with this tool: CORRECTED 13 (5 line, 8 pin)
python3 tools/fn_audit.py IMG256 --scope docs --quiet --drop-pin 0x00542256   # b56fed2: INSIDE 36, CORRECTED 10
python3 tools/fn_audit.py --selftest                           # selftest: OK (83 checks, 0 failed)
```

## Follow-ups

- [ ] When M1.24 merges, run `--parent-of 0x00542256` and append its output to this record's `Pin:` line (an "Overtaken" bullet).
