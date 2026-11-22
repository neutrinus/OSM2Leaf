# EXP-2026-11-22-H130-board-claim-raw-pipe

- **Status:** running
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
   and the selftest's `refused(...)` cases must pass. `claims_check --strict
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

(Post-fix observations to be filled in before the final commit.)

## Interpretation

- **FACT:** the unmodified tool splits the raw pipe into a cell separator and
  writes the row anyway, so the status/confidence/evidence cells shift by one;
  `claims_check` does not flag it.
- **FACT:** the ledger already stores `\|` as a literal pipe and 84 rows have a
  non-7 split, so escaping is the existing convention and a global rewrite is
  out of scope.
- **HYPOTHESIS:** escaping on write plus an exact-7 guard fixes the silent
  corruption — to be confirmed by the post-fix observations.
- **UNKNOWN:** none yet.

## Conclusion

Pending post-fix observations and navigator review.

## Corrections after navigator review

pending review

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/board.py --selftest
python3 tools/gate.py
```

## Follow-ups

- [ ] none
