# EXP-2026-11-22-H130-board-claim-raw-pipe

- **Status:** done
- **Date:** 2026-11-22
- **Sample:** none (tool-only task) — edits `tools/board.py`; the specimen is the
  live ledger row `C-6564`, copied to a scratch path for the precheck. No vendor
  image required.
- **Tools:** `python3 3.13.1` (stdlib `re`), repo tools `tools/board.py`,
  `tools/claims_check.py`, `tools/selftest.py`, `tools/gate.py`
- **Claims:** none added (H130 reserves C-8260–C-8269; tooling fix only)
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `board.py claim-body`/`claim-set` corrupt a claim row when the claim text
contains a raw `|` (e.g. `(0x800|flon, flat)`), and can a row-shape guard plus
an escaped-pipe write convention make the write safe and fail loudly?

## Hypothesis

Yes. `board.py` stores claim text with a literal pipe, but the row reader treats
only an **unescaped** pipe as a cell separator, so the extra pipe shifts every
later cell and `claims_check` still exits 0. The fix is to escape unescaped
pipes in values written by `claim-body`/`claim-set`, to require exactly the 7
split parts of a 5-cell row before any write, and to pin both in the selftest.
Falsifier: if the unmodified `claim-body` with a raw pipe leaves the target row
at 7 cells and the neighbouring rows unchanged, the split is not the defect and
this task is closed negative; if after the fix a `|`-containing write leaves a
row with != 7 cells or the guard misses a wrong cell count, the fix fails.

## Plan (written before code)

- **Exact source of the row grammar (read from `tools/board.py`, not guessed):**
  `ROW_RE = re.compile(r"^\|\s*(C-\d+)\s*\|")`; `_row_cells` at line 707 splits
  with `re.split(r"(?<!\\)\|", line)[1:-1]`; `_claim_row` at line 773 splits
  with the same regex and checks only `len(parts) < 7` (so 8+ parts pass);
  `op_claim_body` (line 808) sets `parts[2] = f" {text.strip()} "` and re-joins
  with `"|".join(parts)`; `op_claim_set` (line 783) searches cells 2 then 5
  with `pat = re.compile(rf"(?<![\w.]){re.escape(key)}{sep}[^|]*")`, replaces
  in place, or appends to cell 2; `op_claim_row` (line 752) checks only
  `len(re.split(...)) < 6`. A well-formed row splits into exactly 7 parts:
  `['', id, body, status, confidence, evidence, '']`. `\|` is already a stored
  escape in the ledger (C-542, C-617, C-1713, …) and in `SAMPLE_CLAIMS`
  (`| C-101 | b \| pipe | … |`), so escaping is the established convention,
  not a new guess.
- **Approach:** add `_check_cells(cid, line)` (exactly 7 parts or `BoardError`)
  used by `_claim_row` and by each write op on the constructed row **before
  `bf.splice`**; add `_escape_pipes(text)` that rewrites only pipes not already
  preceded by `\`; escape the value in `op_claim_body` and `op_claim_set`; change
  the `claim-set` replacement regex from `[^|]*` to `(?:\\\|[^|])*` so an
  existing escaped pipe is consumed as part of the old value instead of being
  turned back into a raw separator; make `op_claim_row` refuse any row whose
  split is not exactly 7 parts (a whole row supplied with a raw pipe is
  ambiguous, so refuse rather than guess where to escape). No ledger row is
  rewritten by hand. "Unescaped on read" is the ledger convention: readers see
  `\|` and strip the backslash to recover the literal pipe; the selftest asserts
  that round-trip.
- **Files:** `tools/board.py` (`_check_cells`, `_escape_pipes`, `_claim_row`,
  `op_claim_body`, `op_claim_set`, `op_claim_row`, `run_selftest`), this EXP,
  own TODO line via `tools/board.py claim`/`done`. No `AGENTS.md` change: the
  ledger already uses `\|`, so no new convention needs recording.
- **Intended Done when:** a `|`-containing body is escaped on write and the row
  still has exactly 7 pipe-split cells with neighbouring rows unchanged;
  wrong-cell-count rows are refused before any write; `--selftest` covers all
  of it; `claims_check --strict --count-check` OK; `gate.py` 5 pass / 0 fail /
  0 skip; `board.py done H130 --result "…"`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only task) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.13.1` |
| Repo tool | `tools/board.py`, `tools/claims_check.py`, `tools/selftest.py`, `tools/gate.py` |

## Method

1. **Sample and hash.** No vendor sample. Specimen: `docs/research/claims.md`
   row `C-6564` at `origin/main` (`ffa54bbb` at claim time); copied to a scratch
   path before the precheck, so the live ledger is untouched. The precheck ran
   on the unmodified tool; the fix was written only after the precheck output
   below was captured.
2. **Commands.**

```bash
cd /home/marek/projekty/OSM2Leaf.task-h130-claim-pipe
mkdir -p /home/marek/projekty/leafre-work/scratch/h130
cp docs/research/claims.md /home/marek/projekty/leafre-work/scratch/h130/claims.md
python3 tools/board.py --claims /home/marek/projekty/leafre-work/scratch/h130/claims.md \
  claim-body C-6564 "a (0x800|flon, flat) pair"
python3 - <<'PY'
import re
for tag, p in [('before', 'docs/research/claims.md'),
               ('after', '/home/marek/projekty/leafre-work/scratch/h130/claims.md')]:
    for l in open(p, encoding='utf-8'):
        if l.startswith('| C-6564 |'):
            print(tag, len(re.split(r'(?<!\\)\|', l.rstrip('\n'))), repr(l.rstrip('\n')[:200]))
PY
python3 tools/claims_check.py --claims /home/marek/projekty/leafre-work/scratch/h130/claims.md

python3 - <<'PY'
import re, collections
lines = open('docs/research/claims.md', encoding='utf-8').read().splitlines()
c = collections.Counter(len(re.split(r'(?<!\\)\|', l)) for l in lines
                        if re.match(r'^\|\s*C-\d+\s*\|', l))
print('claim rows total:', sum(c.values()), 'cells=7:', c[7],
      'cells!=7:', sum(v for k, v in c.items() if k != 7))
print('distribution:', dict(sorted(c.items())))
PY

# after the fix
python3 tools/board.py --selftest
python3 tools/claims_check.py --strict --count-check
python3 tools/gate.py
```

3. **Controls.** Positive: an ordinary `claim-body`/`claim-set` write on a
   well-formed row still succeeds (selftest cases "claim-body replaces only
   cell 1" and "claim-set adds Supersedes to body cell 2"). Negative: a raw
   `|` body on the scratch copy must go from 7 to 8 split parts while
   `claims_check` still exits 0 (precheck); after the fix a raw `|` write must
   stay at 7 parts, a wrong-cell-count row must be refused before any write,
   and the selftest's `run(...) == 1` refusal cases must pass. `claims_check --strict
   --count-check` and `gate.py` are the standing regression controls.
4. **Scope.** Covered: `tools/board.py` `_claim_row`, `op_claim_body`,
   `op_claim_set`, `op_claim_row`, their helpers and selftests; live ledger row
   `C-6564` only on a copy. Not covered: `op_claim_status`/`op_add_claims`
   (unchanged, not in task scope), and the 84 pre-existing ledger rows whose
   split is not 7 parts — they are not rewritten; the new guard will refuse
   writes to them until they are repaired by hand with `claim-row` in a task
   that owns them.
5. **Falsifier.** Before the fix: raw-pipe `claim-body` leaves 7 cells and all
   neighbouring rows unchanged. After the fix: any `|`-containing write leaves
   != 7 cells, a wrong-cell-count row is written anyway, the selftest passes
   with the guard removed, `claims_check --strict --count-check` fails, or
   `gate.py` is not 5 pass / 0 fail / 0 skip.

## Observations

(Precheck, captured before code.)

`python3 tools/board.py --claims COPY claim-body C-6564 "a (0x800|flon, flat) pair"`:
`board: C-6564 body replaced`.

Split counts for `C-6564` printed by the inline script: `before 7`; `after 8`.
The after row begins
`'| C-6564 | a (0x800|flon, flat) pair | VERIFIED | H | EXP-2026-11-22-M4.61-point-ids; ... |'`.

`python3 tools/claims_check.py --claims COPY`: `claims_check: OK` (exit 0).

Ledger cell-count census: `claim rows total: 3409 cells=7: 3325 cells!=7: 84`;
`distribution: {6: 6, 7: 3325, 8: 61, 9: 4, 10: 5, 11: 3, 12: 2, 13: 2, 14: 1}`.
`C-6564` on the live ledger: `7`.

(Post-fix, all quoted from the commands that printed them.)

`python3 tools/board.py --selftest`: `board selftest: OK (105 checks)`
(was 89 before the 16 new H130 checks).

Same precheck command on a fresh copy after the fix: `board: C-6564 body
replaced`; split counts `before cells 7 body 'No \`ADDRE\` record carries a
POINT-style (0x800 + flon, flat) pair …'` and
`after cells 7 body 'a (0x800\\|flon, flat) pair'`. The literal pipe is stored
escaped and the neighbouring cells (status, confidence, evidence) keep their
positions. `python3 tools/claims_check.py --claims COPY`: `claims_check: OK`.

Guard, on a copy whose C-6564 row was made to have 9 split parts:
`board: refused: C-6564: row has 7 cells (need exactly 5)` for both `claim-body`
and `claim-set`, `exit=1` each; `claim-row` with an 8-part row printed
`board: refused: C-6564: row has 6 cells (need exactly 5)`, `exit=1`. The row
stayed at 9 split parts after all three refusals.

`python3 tools/board.py lost --base origin/main`: `TODO.md: OK tasks=0
claims=0`, `docs/research/claims.md: OK tasks=0 claims=0`, `lost exit=0`.
`python3 tools/claims_check.py --strict --count-check`: `claims_check: OK`,
`exit=0`. `python3 tools/todo_check.py`: `todo_check: OK`, `exit=0`.

Two gate runs during this session failed only on untouched tools while the host
was under load ~18 on 8 cores: `tool:ci_gate_repro FAIL timeout after 60s` and
`tool:mkcard FAIL exit 1 (ENOSPC on the 98 %-full /tmp)` in the first, then
`tool:ci_gate_repro FAIL timeout after 60s` and `tool:lev3456gen FAIL exit -9`
(OOM kill) in the second. `board_check`, `claims_check`, `todo_check` and
`fn_audit` were PASS in both. `python3 tools/ci_gate_repro.py --selftest` with
`TMPDIR` on the home tree printed `ci_gate_repro selftest: OK …`; the same
command without it died with `OSError: [Errno 28] No space left on device`.
A third gate run printed `selftest FAIL; claims_check/todo_check/board_check/
fn_audit PASS` = `gate: 4 pass, 1 fail, 0 skip`; a fourth (load 5.97) printed

```
selftest      PASS    199.11
claims_check  PASS     18.13
todo_check    PASS      0.08
board_check   PASS      0.22
fn_audit      PASS      5.29
gate: 5 pass, 0 fail, 0 skip
gate exit=0
```

## Interpretation

- **FACT:** the unmodified tool splits the raw pipe into a cell separator and
  writes the row anyway, so the status/confidence/evidence cells shift by one;
  `claims_check` does not flag it.
- **FACT:** the ledger already stores `\|` as a literal pipe and 84 rows have a
  non-7 split, so escaping is the existing convention and a global rewrite is
  out of scope.
- **FACT:** after the fix the raw-pipe body is stored as `\|`, the row stays at
  7 cells and both neighbouring rows are byte-identical; a 6- or 8-cell row is
  refused with `board: refused: C-6564: row has N cells (need exactly 5)` and
  exit 1, leaving the file unchanged.
- **OBSERVED:** `board selftest: OK (105 checks)`, `claims_check: OK` under
  `--strict --count-check`, `board.py lost --base origin/main` exit 0, and
  `gate: 5 pass, 0 fail, 0 skip`. The earlier gate failures were host load and
  `/tmp` pressure on untouched tools (`ci_gate_repro`, `mkcard`, `lev3456gen`),
  not this change.
- **HYPOTHESIS:** none.
- **UNKNOWN:** none.

## Conclusion

H130 is fixed: `claim-body` and `claim-set` escape raw pipes on write, the
reader treats `\|` as literal, and `_check_cells` refuses any row that is not
exactly five cells before any write. `op_claim_row` refuses a whole row with a
raw pipe instead of guessing. The selftest pins escaping, unescaped read-back,
unchanged neighbours and both wrong-cell-count refusals. No ledger row was
rewritten by hand and no `AGENTS.md` change was needed: the escape convention
already existed in the ledger.

## Corrections after navigator review

pending review

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/board.py --selftest          # board selftest: OK (105 checks)
python3 tools/claims_check.py --strict --count-check   # claims_check: OK
python3 tools/gate.py                      # gate: 5 pass, 0 fail, 0 skip
```

On a loaded host set `TMPDIR` to a home-tree scratch dir for the gate run: a
98 %-full `/tmp` tmpfs killed unrelated `mkcard`/`ci_gate_repro` selftests with
ENOSPC during this session.

## Follow-ups

- [ ] none
