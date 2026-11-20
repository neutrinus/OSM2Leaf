# EXP-2026-11-20-H118: `fn_match` slot pass ignores pool data that no load names

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU2011 firmware head, IMG256, 256 MiB,
  SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`)
  and `archive/us256.img` (US2011 head, US256, 256 MiB, SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`)
- **Tools:** Python 3.13.18; `tools/fn_match.py`, `tools/nomatch_census.py`,
  new `tools/fn_verdict_diff.py` (branch `task/h118-fnmatch-unloaded-pool`);
  the "before" side is the same `tools/` at `origin/main` `d8e838f`
  (H113 merged), extracted with `git archive`
- **Claims:** C-5800–C-5806
- **Supersedes:** none (closes the residual in EXP-2026-11-20-H113-fnmatch-pool)
- **Superseded by:** none

## Question

How many `fn_match` rows does pool data that **no** load names still corrupt
after H113's forward pass, and does a control-flow rule remove it without
moving any matched US address?

## Hypothesis

H113 exempts only a pool word a load already named. Data that no load names
(trailing pool runs, doubles reached by `mova`, alignment) still decodes as
`mov.x @(disp,PC)` and either blanks a real instruction or pulls bytes
from **past the function** into pass 3 of `fingerprint` (the "pool value" is
then another function's relocated bytes). A static walk from the entry
separates code from data in two safe ways:

- **target rule:** a slot never lies on a halfword the entry reaches
  (fall-through, `bt`/`bf`(`/s`), `bra`, delay slots; `rts`/`rte`/`braf`/`jmp`
  end a path);
- **closed rule:** in a function with **no reached `braf`/`jmp`** nothing can
  hide code from the walk, so an unreached halfword is data and names no slot.
  A function with a reached computed jump keeps its unreached loads (switch
  case bodies).

**Falsifier:** any row whose non-null US address becomes another non-null US
address (H113/H118 Stop); or any `UNIQUE` row that stops being `UNIQUE`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (EU2011), `archive/us256.img` (US2011) |
| SHA-256 | `92aa525d…a007f9` / `70d945d8…06a04da` |
| Corpus | `Navi.exe` build A `.pdata`: 7596 EU records, 7520 US records; 89,567 / 87,830 PC loads under the H113 pass |
| Tool / version | `tools/fn_match.py` (`reachable`, `is_computed_jump`, `_pool_loads`), `tools/fn_verdict_diff.py` |
| Repo tool | `tools/fn_verdict_diff.py` (`dump`, `diff`, `slots`, `--all-closed`) |

## Method

1. **Sample and hash.** The two heads above; every EU `.pdata` record of
   `Navi.exe` (7596) is one row.
2. **Commands** (from the worktree root; `S` is any scratch directory):

   ```bash
   S=$(mktemp -d); mkdir -p "$S/before"
   git archive d8e838f tools | tar -x -C "$S/before"
   python3 tools/fn_verdict_diff.py dump archive/head256.img archive/us256.img -o "$S/before.json" --tools "$S/before/tools"
   python3 tools/fn_verdict_diff.py dump archive/head256.img archive/us256.img -o "$S/after.json"
   python3 tools/fn_verdict_diff.py diff "$S/before.json" "$S/after.json" --rows
   python3 tools/fn_verdict_diff.py slots archive/head256.img archive/us256.img --verdicts "$S/before.json"
   python3 tools/fn_verdict_diff.py dump archive/head256.img archive/us256.img -o "$S/ablate.json" --all-closed
   python3 tools/fn_verdict_diff.py diff "$S/before.json" "$S/ablate.json"
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all
   python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json --eu archive/head256.img --us archive/us256.img
   python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va 0x0033d00c 0x00422188
   python3 tools/fn_match.py bodies archive/head256.img archive/us256.img --fixture-rows tools/fixtures/fn_match_eu_us_2011.json
   python3 tools/fn_match.py --selftest
   python3 tools/fn_verdict_diff.py --selftest
   python3 tools/nomatch_census.py --selftest
   ```

3. **Controls.**
   - *Positive (synthetic, the task's case):* `fn_match --selftest` builds
     `hw0 = 0xD702` (loads hw6), `hw6 = 0xDA39` (loaded, exempt), `hw50 =
     0xD023` (named by no load, would name hw122), `hw122 = 0xC11E` in a
     function with no computed jump, and asserts `122 not in pool_slots`,
     `_instruction_tokens[122] == c11e`, `pool_masked[122] == 0xC11E`, while
     the loaded pool word (hw6) and the real load at hw10 still blank their
     slots. With the two H118 lines removed from `_pool_loads` the three H118
     checks fail (`FAIL (53 checks, 3 failed)`, observed on a scratch copy).
   - *Target rule alone:* a `bra` over a mid-function pool to code that runs
     over hw122 to a `braf` (open function): `122 not in pool_slots`.
   - *Out-of-function read:* `rts; nop; 0x999a; 0x9999` (the double `0.1`):
     `pool_slots == {}` and flipping a byte past the function leaves the
     `fingerprint` unchanged.
   - *Negative (synthetic):* the same hw50 function with a reached `braf`
     keeps hw50's slot (`122 in pool_slots`): unreached code behind a
     computed jump is not trusted to be data.
   - *Negative (real image, ablation):* `dump --all-closed` drops every
     unreached load, switch case bodies included; it must lose matches.
   - *Pipeline:* the 13-row fixture and the 12-pair `bodies` table must not
     change.
4. **Scope.** `tools/fn_match.py` slot derivation (`_pool_loads` and the new
   `reachable`/`is_computed_jump`), hence `pool_slots`, `fingerprint`,
   `_instruction_tokens`/`code_digest`, `pool_masked`; the H113 selftest
   synthetic gains a `bt` so its "real load" at hw10 is on a path; module
   `Navi.exe` only, both builds. Not: `_pool_only_twin`/twin anchoring (H114),
   the leaf search window, `mova` targets as slots, any other module.
5. **Falsifier.** As in Hypothesis.

## Observations

### Census, all 7596 EU functions (`fn_verdict_diff diff`)

| | UNIQUE | DIFFERENT | CALLORDER | AMBIGUOUS | NOMATCH |
| --- | --- | --- | --- | --- | --- |
| before (H113, `d8e838f`) | 5945 | 171 | 56 | 566 | 858 |
| after (H118) | 5954 | 162 | 56 | 566 | 858 |

Transitions: `DIFFERENT -> UNIQUE 9`; unchanged rows `7587`;
`B address moved to another non-null B: 0`. The nine rows, each to the same
US VA as before (EU2011 → US2011):

`0x00422188→0x00449a64`, `0x0042d7d4→0x00454dd0`, `0x00431fc0→0x00459544`,
`0x0045b5f8→0x0048546c`, `0x00460360→0x00489a74`, `0x00470950→0x00498ee0`,
`0x004870d4→0x004aa070`, `0x00487e6c→0x004aada8`, `0x004a1bd0→0x004c4d5c`.

`nomatch_census.py --all` (after): `# census: UNIQUE 5954  DIFFERENT 162
CALLORDER 56  AMBIGUOUS 566  NOMATCH 858  total 7596`; classes `TWIN 14
PHANTOM-SLOT 0 … IMMEDIATE 68 OPERANDS 1 EDIT 147 REWRITE 299 UNPAIRED 329`.

### Residual counted (`fn_verdict_diff slots --verdicts before.json`)

```
# A: 7596 functions, 89567 H113 loads; dropped: target 27  unreached 233  in 102 functions; gained 3
# B: 7520 functions, 87830 H113 loads; dropped: target 22  unreached 218  in 98 functions; gained 3
# rows with a dropped load on either side (EU side only when the row has no B address): UNIQUE 45/5945  DIFFERENT 10/171  CALLORDER 7/56  AMBIGUOUS 13/566  NOMATCH 31/858
```

`gained` counts halfwords H113 had masked as slots that H118 unmasks and
keeps as real loads (3 per build). A NOMATCH row has no US address, so
only its EU function is checked.

In the nine changed rows the dropped loads are identical in EU and US
(same index, same word), e.g. `0x00422188`: `i=246 9d39`, `i=248 df46`,
`i=252 d45e`, all past the last reached halfword (226) with slots past the
function end (len 254); five rows drop `999a 9999 9999` (the low word of the
double `0x3fb999999999999a`, 0.1) past the last reached halfword. Eight of nine have every
dropped slot outside the function; `0x004a1bd0` has one inside
(`i=170 9513 → hw191`, len 198).

### Ablation (`dump --all-closed`, negative control)

`UNIQUE 5890  DIFFERENT 159  CALLORDER 61  AMBIGUOUS 576  NOMATCH 910`;
transitions `UNIQUE→NOMATCH 48`, `UNIQUE→AMBIGUOUS 11`, `UNIQUE→CALLORDER 5`,
`DIFFERENT→UNIQUE 9`, `DIFFERENT→NOMATCH 3`, `AMBIGUOUS→NOMATCH 1`; moved 0.

### Fixture, bodies, spot checks, selftests

- Fixture replay: `13 rows, 0 mismatch` (fixture unchanged, SHA-256
  `68b78680…e11`).
- `bodies --fixture-rows`: `summary: 12/12 identical masked form stream;
  negatives 0; problems 0`, byte-identical output to the `d8e838f` tools.
- `match --va 0x0033d00c 0x00422188`: `UNIQUE → 0x0036bb5c` (H113's row,
  unchanged) and `UNIQUE → 0x00449a64` (was `DIFFERENT`).
- `fn_match --selftest`: `OK (53 checks, 0 failed)` (46 at `d8e838f`, +7
  H118); `fn_verdict_diff --selftest`: `OK (11 checks, 0 failed)`;
  `nomatch_census --selftest`: `OK (20 checks, 0 failed)`.

## Interpretation

- **FACT:** pool data no load names corrupted 9 of 171 `DIFFERENT` rows
  (5.3 %) and **0 of the 858 `NOMATCH`** verdicts: 31 NOMATCH rows contain such
  a load, but removing it does not give any of them a US hash partner.
- **FACT:** the corruption in the real image is mostly the out-of-function
  read, not the in-function blank: 8 of the 9 rows have only slots past the
  function end, whose "pool value" is the next function's relocated bytes.
  The in-function blank the H113 record described (task synthetic) exists
  (27 EU / 22 US loads hit a reached instruction) but moves no verdict.
- **FACT:** the rule is a refinement only: 0 moved US addresses, 0 rows
  leave `UNIQUE`, fixture and bodies table unchanged.
- **FACT (control):** the closed-function guard is necessary: dropping every
  unreached load loses 64 `UNIQUE` rows (48 to `NOMATCH`), the switch-table
  case bodies a `braf`/`jmp` reaches.
- **HYPOTHESIS:** the 858 NOMATCH are not a slot problem any more; their mix
  (`TWIN 14`, `EDIT 147`, `REWRITE 299`, `UNPAIRED 329`) is real code change
  or pairing, which H114 and the classifier address.
- **UNKNOWN:** code reached only by an in-function `bsr` or by an SEH
  `__except` handler counts as unreached, so in a "closed" function its real
  loads are dropped. No row of this corpus is affected (navigator probe), but
  another module could be.
- **UNKNOWN:** whether `mova` targets (multi-word constants such as the
  doubles above) should be masked as pool data; today their bytes are hashed
  as instructions, identically on both sides.

## Conclusion

`fn_match._pool_loads` now uses a static walk (`reachable`) and rejects a
slot on a reached instruction and, in a function with no reached
`braf`/`jmp`, any load at an unreached halfword. The H113 residual (C-5570)
is closed: the task's hw50 synthetic no longer blanks hw122, the loaded-pool
case still does not, and the census moves `DIFFERENT 171 → 162`,
`UNIQUE 5945 → 5954` with no other change; NOMATCH stays 858 (the residual
explains none of them). Claims C-5800–C-5806; C-5571's census is historical
for the 9 rows.

## Corrections after navigator review

Round 1: no blockers, 2 should-fix, 4 nits. All six were fixed on this branch:

1. *(should-fix)* C-5571's census was stale for the 9 rows and not marked
   historical. It now carries "Historical for 9 rows: H118 supersedes it with
   5954/162/56/566/858 (C-5801)", the same way C-3626 is marked.
2. *(should-fix)* C-5570 still said "Residual (open)" next to "Closed by
   H118". It is reworded as closed, and its `OK (46 checks …)` evidence is now
   marked "at `d8e838f`; 53 after H118".
3. *(nit)* `fn_verdict_diff.dropped` did not count the loads H118 newly keeps
   once a slot is unmasked. `slots` now prints `gained 3` for each build
   (Observations, C-5802).
4. *(nit)* "on either side" was inaccurate for NOMATCH rows, which have no B
   address. The `slots` header, the Observations and C-5802 now say that only
   the EU side is checked for those rows.
5. *(nit)* `reachable` treats code reached only by an in-function `bsr` or an
   SEH `__except` handler as unreached. This is now stated in its docstring
   and under UNKNOWN in Interpretation. The navigator's probe found no effect
   in this corpus.
6. *(nit)* Method used a personal scratch path. It now uses `S=$(mktemp -d)`.

The navigator re-ran the census, the selftest (53), the fixture (0 mismatch),
the gate (4/4) and the falsifier (0), and got the same numbers. None of the
fixes changes a verdict.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all
# expected: # census: UNIQUE 5954  DIFFERENT 162  CALLORDER 56  AMBIGUOUS 566  NOMATCH 858  total 7596
python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json \
    --eu archive/head256.img --us archive/us256.img   # expected: 13 rows, 0 mismatch
python3 tools/fn_match.py --selftest                 # expected: OK (53 checks, 0 failed)
```

## Follow-ups

- [ ] H114 (other TL, PR #339) re-takes its TWIN counts on this census if it
  merges after this record (the slot change moves 9 `DIFFERENT` rows only;
  NOMATCH is unchanged at 858).
