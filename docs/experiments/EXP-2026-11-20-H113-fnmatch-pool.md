# EXP-2026-11-20-H113: `fn_match` forward slot pass (the PHANTOM-SLOT false blanks)

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU2011 firmware head, 256 MiB, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`) and
  `archive/us256.img` (US2011 head, 256 MiB, SHA-256
  `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`)
- **Tools:** Python 3.15.0, `tools/fn_match.py`, `tools/nomatch_census.py`
  at their H113 revision; the "before" numbers were produced by the same
  tools at `origin/main` `d2fb7b4` extracted with
  `git archive d2fb7b4 tools | tar -x -C DIR` and run as
  `PYTHONPATH=DIR/tools python3 DIR/tools/nomatch_census.py …`
- **Claims:** C-5570–C-5576
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `fn_match`'s pool-slot derivation blank real instructions (H89's
`PHANTOM-SLOT` class, C-4123), and what does a forward-pass slot derivation
change in the EU→US `Navi.exe` verdict census?

## Hypothesis

`fingerprint`, `_instruction_tokens` and `pool_masked` derive a slot from
every halfword that decodes as `mov.x @(disp,PC)`, including halfwords that are
themselves pool data. A pool word whose low half is `0x9nnn`/`0xDnnn` then
names a slot on a real instruction, which is hashed as `0x0000`. A forward pass
(a halfword already marked as a slot is data and never names another slot; a
PC load's displacement is unsigned, so slots are always marked before the scan
reaches them) removes exactly that class.

**Falsifier:** if the forward pass changes any *previously* `UNIQUE` pair's US
address, the pass is not a pure refinement of the mask but moves a confirmed
match; the change is then wrong for `UNIQUE` and must be stopped (H113 Stop).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img`, `archive/us256.img` |
| SHA-256 | `92aa525d…a007f9` / `70d945d8…06a04da` (fixture-pinned) |
| Corpus | `Navi.exe` build A `.pdata` 7596 records / 7520 records |
| Tool / version | `tools/fn_match.py`, `tools/nomatch_census.py` (branch `task/h113-fnmatch-pool`) |
| Repo tool | the two above, plus the `d2fb7b4` copies for "before" |

## Method

1. **Sample and hash.** The two 256 MiB heads above; every EU `.pdata` record
   of `Navi.exe` (7596) is one row.
2. **Commands.** Run as written from the worktree root:

   ```bash
   # before (origin/main d2fb7b4 tools, extracted to DIR)
   D=$(mktemp -d); git archive d2fb7b4 tools | tar -x -C "$D"
   PYTHONPATH="$D/tools" python3 "$D/tools/nomatch_census.py" archive/head256.img archive/us256.img --all
   # after (branch tools)
   python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all
   python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va 0x0033d00c
   python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json \
       --eu archive/head256.img --us archive/us256.img
   python3 tools/fn_match.py --selftest
   python3 tools/nomatch_census.py --selftest
   ```

   The before/after verdict transition table below comes from dumping every
   `Matcher.verdict()` row in both trees to JSON and diffing the two maps
   (the identical script, so the diff is the tool change alone):

   ```bash
   cat > /tmp/opencode/h113-verdicts.py <<'PY'
   import sys, json, contextlib, io
   sys.path.insert(0, sys.argv[1])              # a tools/ directory
   import fn_match as fm
   with contextlib.redirect_stdout(io.StringIO()):
       m = fm.Matcher("archive/head256.img", "archive/us256.img", "Navi.exe",
                      0x200200, 2, 2, None, None)
   out = {}
   with contextlib.redirect_stdout(io.StringIO()):
       for va, _w, _lr, _cb, _cc in m.fa:
           r = m.verdict(va)
           out["%#010x" % va] = {"v": r[2],
                                 "b": None if r[1] is None else "%#010x" % r[1]}
   json.dump(out, open(sys.argv[2], "w"), sort_keys=True)
   PY
   python3 /tmp/opencode/h113-verdicts.py "$D/tools" /tmp/opencode/before.json
   python3 /tmp/opencode/h113-verdicts.py tools /tmp/opencode/after.json
   python3 - <<'PY'
   import json
   from collections import Counter
   b = json.load(open("/tmp/opencode/before.json"))
   a = json.load(open("/tmp/opencode/after.json"))
   assert set(b) == set(a)
   print("US changed to another non-null US:",
         sum(1 for k in b if b[k]["b"] and a[k]["b"] and a[k]["b"] != b[k]["b"]))
   print(Counter((b[k]["v"], a[k]["v"]) for k in b))
   PY
   ```
3. **Controls.**
   - *Positive:* `--selftest` of `fn_match` builds the crammed pool word
     `0xda39` (low half `0xda39`/`0x0039` = `mov.l @(9,pc),r10`) **loaded**
     by the `mov.l @(2,pc),r7` at hw 0, and asserts the forward pass does
     **not** mark the real instruction at hw 122
     (`H113: forward pass marks the real slots and not the phantom one`), that
     the pool word *would* name it (`… would name hw122`), that a changed real
     instruction still changes the `fingerprint` hash (`… still changes the
     hash`), that `_instruction_tokens` emits the real halfword and `0x0000` for
     the real slots (`… hashes as itself, not as 0x0000`), and that
     `pool_masked` still zeroes a real load's slot (`… still zeroes a real
     load's slot`).
   - *Negative:* the same table run at `d2fb7b4` prints 41 checks and the old
     `pool` behaviour; the fixture replay pins every row (see Observations).
   - *Pipeline:* the H89 anchor/classifier controls are unchanged by this task
     (`38/40` anchor control, `EDIT 2 REWRITE 1 UNPAIRED 37` classifier control,
     same as C-4121).
4. **Scope.** `tools/fn_match.py` slot derivation and its three consumers
   (`fingerprint`, `_instruction_tokens`/`code_digest`, `pool_masked`), the
   `nomatch_census.pool_slots` duplicate (now one function), the H113 selftest
   case, and the re-pinned 13-row fixture. Not: the leaf path, `_pool_only_twin`
   verdict semantics (still `DIFFERENT`), or any file format.
5. **Falsifier.** As in Hypothesis.

## Observations

### Census, all 7596 EU functions (`nomatch_census.py --all`)

| | UNIQUE | DIFFERENT | CALLORDER | AMBIGUOUS | NOMATCH | total |
| --- | --- | --- | --- | --- | --- | --- |
| before (`d2fb7b4`) | 2392 | 3214 | 213 | 518 | 1259 | 7596 |
| after (H113) | 5945 | 171 | 56 | 566 | 858 | 7596 |

Old-NOMATCH population (the H89 1259):

| after verdict | rows |
| --- | --- |
| NOMATCH | 858 |
| UNIQUE | 191 |
| AMBIGUOUS | 174 |
| DIFFERENT | 12 |
| CALLORDER | 24 |

Before→after verdict transitions, all 7596 rows:

| before | after UNIQUE | DIFFERENT | CALLORDER | AMBIGUOUS | NOMATCH |
| --- | --- | --- | --- | --- | --- |
| UNIQUE 2392 | 2386 | 0 | 0 | 6 | 0 |
| DIFFERENT 3214 | 3028 | 159 | 12 | 15 | 0 |
| CALLORDER 213 | 191 | 0 | 20 | 2 | 0 |
| AMBIGUOUS 518 | 149 | 0 | 0 | 369 | 0 |
| NOMATCH 1259 | 191 | 12 | 24 | 174 | 858 |

Rows whose US address changed while staying non-null: **0** (the Stop
condition did not fire). The 6 old-`UNIQUE` rows that are now `AMBIGUOUS`
(`0x003ee10c`, `0x0042af5c`, `0x004e0afc`, `0x004e0b18`, `0x004e0c04`,
`0x0050aae0`) are inside duplicated function runs: their B digest now has
2/3/18 candidates (EU twins too), so the exact-hash rule reports `AMBIGUOUS`
and never guesses; no candidate is lost relative to the old US pick.

### `nomatch_census.py --all` population table

before: `same code 360`, `operand-only 81`, `instruction changes 474`,
`unpaired 344`, `forward-pass digest unique in US: 141 of 1259`.
after: NOMATCH is 858; `same code 14`, `operand-only 69`,
`instruction changes 446`, `unpaired 329`, and `forward-pass digest unique in
US: 0 of 858` (the label is now vacuous: `fn_match.code_digest` is already the
forward pass, so no NOMATCH has a unique fixed digest by construction).

Of the old 141 rows that the forward-pass digest named uniquely in US, **129
are now `UNIQUE` to that same US function** and **12 are `DIFFERENT`** (masked
form stream equal, pool values differ), i.e. the same US function in 141/141;
none is a different US address.

### H89 sample (`--seed 89 --size 40`, same seed)

before: `TWIN 13 PHANTOM-SLOT 3 IMMEDIATE 4 EDIT 7 REWRITE 5 UNPAIRED 8`
(sample of 1259: `# sample: seed 89 size 40 of 1259`).
after: `TWIN 1 IMMEDIATE 2 EDIT 1 REWRITE 20 UNPAIRED 16`
(`# sample: seed 89 size 40 of 858`). The sample is drawn from a smaller
population, so its class mix is not comparable row-for-row.

### Where the 3028 `DIFFERENT`→`UNIQUE` rows came from

For each such row the EU/US function was scanned for an *old load instruction*
that the forward pass now marks as pool data (a halfword `i` with
`is_mov_pc`, `i` now in `pool_slots`, in either build): `EU only 1139`,
`US only 844`, `both 1045`, `neither 0`. So every one of the 3028 is a phantom
slot in one of the two builds; none is an unrelated hash move. (The same scan
over the 191 `NOMATCH`→`UNIQUE` rows: `both 113`, `US only 46`, `EU only 32`.)

```bash
python3 - <<'PY'
import sys, json, contextlib, io
sys.path.insert(0, "tools")
import fn_match as fm
b = json.load(open("/tmp/opencode/before.json"))
a = json.load(open("/tmp/opencode/after.json"))
with contextlib.redirect_stdout(io.StringIO()):
    m = fm.Matcher("archive/head256.img", "archive/us256.img", "Navi.exe",
                   0x200200, 2, 2, None, None)
def dropped(ws, va):
    fw = fm.pool_slots(ws, va)
    return sum(1 for i, w in enumerate(ws) if i in fw and fm.is_mov_pc(w))
from collections import Counter
for old, new in (("DIFFERENT", "UNIQUE"), ("NOMATCH", "UNIQUE")):
    c = Counter()
    for k, v in b.items():
        if v["v"] != old or a[k]["v"] != new:
            continue
        va = int(k, 16)
        e = m._fa_by_va[va]
        bb = m._fb_by_va[int(a[k]["b"], 16)]
        c[(dropped(e[0], va) > 0, dropped(bb[0], int(a[k]["b"], 16)) > 0)] += 1
    print(old, "->", new, dict(c))
PY
```

### `0x0033d00c` and the fixture

`fn_match.py match … --va 0x0033d00c` now prints
`UNIQUE … -> 0x0036bb5c` (was `NOMATCH`).
The 13-row fixture replays `13 rows, 0 mismatch` with 6 former `DIFFERENT` rows
re-pinned to `UNIQUE` (same US VA, same `+0xcc`/`+0x2d0`/…-class diff earlier
now genuinely identical: the differing literal is a pool *data* halfword that
the old pass read as a load). The POINT walker row `0x003f5194` stays
`DIFFERENT → 0x0041db44` at `+0x14` (leaf path compares pool *values*; that
constant really moved, C-3701).

`fn_match.py --selftest`: `OK (46 checks, 0 failed)` (was 41 at `d2fb7b4`);
`nomatch_census.py --selftest`: `OK (20 checks, 0 failed)`.

## Interpretation

- **FACT:** the old slot pass blanked real instructions in both builds. The
  forward pass changes 3214 `DIFFERENT` and 518 `AMBIGUOUS` EU functions to
  `UNIQUE` because their old "diff" was a phantom-slot blank, not code.
- **FACT:** forward-pass marking is not a pure refinement: a halfword can be a
  load in one build and pool data in the other, so the pass overrides the naive
  pass *both* ways. The `+0xcc`/`+0x2d0` rows show this exactly (a literal at
  the function end whose low half decodes as a load).
- **FACT:** every one of the 3028 `DIFFERENT`→`UNIQUE` rows has an old load
  instruction that is now pool data; 0 has neither, so the hash move is not a
  spurious collision explanation.
- **OBSERVED:** 6 old `UNIQUE` rows became `AMBIGUOUS`; each is inside a run of
  duplicate functions (B digest 2–18 candidates). The old pairing was one of
  the twins; the exact-hash rule now refuses to pick one.
- **HYPOTHESIS:** part of the remaining 858 NOMATCH is the same "pool data
  decodes as a load" problem one level deeper (the forward pass over-keeps the
  pool *contents* of a function whose trailing data is not pointed at by any
  load), and part is the TWIN class (H114).
- **UNKNOWN:** whether `_pool_only_twin` (masked-form `DIFFERENT`) is the right
  verdict for the 12 old-NOMATCH rows that stay `DIFFERENT`.
- **FACT (residual, not closed):** the mark-only rule exempts a pool word that
  a load has **already named**. *Unloaded* pool data (a data run no load
  points at) that decodes as `mov.x @(disp,PC)` still names a slot and blanks a
  real instruction. Synthetic control: `hw0 = 0xD702` (loads hw6), `hw6 =
  0xDA39` (loaded, exempt), `hw50 = 0xD023` (named by no load), `hw122 =
  0xC11E`; `pool_slots` contains 122 (`50 not in slots`), `_instruction_tokens
  [122] == 0x0000`, `pool_masked[122] == 0`. So the H113 title class is only
  closed for loaded pool words; the unloaded-data case is open (Follow-ups).

## Conclusion

`pool_slots`/`_pool_loads` in `tools/fn_match.py` now find slots in one forward
pass and feed `fingerprint`, `_instruction_tokens`/`code_digest` and
`pool_masked`; `nomatch_census.pool_slots` delegates to it. The rule is
mark-only: it closes the class for a pool word a load already names, **not**
for unloaded pool data that decodes as a load (H118, filed by the navigator's
review). C-3626's
`DIFFERENT 3214 / UNIQUE 2392 / …` is historical (measured at `d2fb7b4`); the
module census is now `UNIQUE 5945 / DIFFERENT 171 / CALLORDER 56 / AMBIGUOUS
566 / NOMATCH 858`. The fixture is re-pinned (6 rows `DIFFERENT`→`UNIQUE`, same
US addresses), `fn_match --selftest` 41→46 checks. H114's twin counts must be
re-taken on top of this (it depends on H113 for exactly that reason).

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_match.py match archive/head256.img archive/us256.img \
    --module Navi.exe --va 0x0033d00c        # expected: UNIQUE -> 0x0036bb5c
python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json \
    --eu archive/head256.img --us archive/us256.img  # expected: 13 rows, 0 mismatch
python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all
# expected: # census: UNIQUE 5945  DIFFERENT 171  CALLORDER 56  AMBIGUOUS 566  NOMATCH 858  total 7596
python3 tools/fn_match.py --selftest        # expected: OK (46 checks, 0 failed)
```

## Follow-ups

- [ ] H114: re-take the TWIN counts (219 at `d2fb7b4`) on this census; the
  population is now 858, not 1259.
- [ ] Re-run the H89 `--seed 89` sample on the new population if a class mix is
  wanted; the old sample is not comparable.
- [ ] H118 (filed by the navigator's review): the **unloaded** pool-data
  residual above — measure it among the 858 NOMATCH and narrow the slot rule.
  The H113 title class is therefore **not** fully closed: this record closes
  the class for pool words a load already names.
