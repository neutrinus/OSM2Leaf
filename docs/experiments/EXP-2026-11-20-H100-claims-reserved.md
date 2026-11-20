# EXP-2026-11-20-H100: RESERVED placeholder rows become a gate-visible state

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** none (tool-only task: `docs/research/claims.md` + `TODO.md` are
  checked-in text, no vendor bytes)
- **Tools:** `python3 3.15.0`; repo tools `tools/claims_check.py`,
  `tools/todo_check.py`, `tools/gate.py`
- **Claims:** C-5970, C-5971, C-5972, C-5973
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a `RESERVED (<TASK>).` placeholder row be made a *gate-visible* state that
fails when its owner task is `done` or absent from `TODO.md`, and can the rows
whose owner is `done`/absent be retired without renumbering any real claim or
moving `--count-check`?

## Hypothesis

The ledger's ten-row-per-block placeholders (`| C-xxxx | RESERVED (TASK). | — |
— | — |`) are text, so `claims_check` never saw them: a `done` owner did not
retire its block, and a free-ID scanner read "reserved" as "registered". A
strict-shape parser (whole claim cell is `RESERVED (<owner>).`, status and
evidence both `—`) plus the board's own status map (`todo_check._parse_status`)
can name a dead block loudly, and deleting those rows is safe because a
placeholder carries no claim ID that any `Supersedes:`/`Superseded by:` pointer
names.

- **Falsifier:** if deleting the `done`/absent rows changes `--count-check`'s
  mismatch count (those rows are not count-bearing), or if any `Supersedes:`/
  `Superseded by:` pointer in the ledger names a deleted ID, the "safe to
  delete" half is wrong and the rows must be retained (`OBSERVED retained`).

## Inputs

| Item | Value |
| --- | --- |
| Ledger | `docs/research/claims.md` (4262 lines before, 3974 after) |
| Board | `TODO.md` (`Status:` of every task, via `todo_check`) |
| Parser | `tools/claims_check.py` row parser, `row_cells`, `todo_check._parse_status` |
| Baseline revision | `2e683be` (`origin/main` at claim time) |

## Method

1. **Sample and hash.** No vendor sample; the corpus is the checked-in
   `docs/research/claims.md` and `TODO.md` at `2e683be`. This is a tool/text
   task, so there is no byte range to pin — every number below is printed by a
   committed command against those files.
2. **Commands.** Runnable as written from the repository root:

   ```bash
   # pre-fix census of the ledger at the baseline revision, with the new parser
   git show 2e683be:docs/research/claims.md > /tmp/h100-pre.md
   python3 tools/claims_check.py --reserved-census --claims /tmp/h100-pre.md
   python3 tools/claims_check.py --strict --claims /tmp/h100-pre.md ; echo $?

   # post-fix ledger
   python3 tools/claims_check.py --reserved-census
   python3 tools/claims_check.py --strict ; echo $?
   python3 tools/claims_check.py --strict --count-check
   python3 tools/claims_check.py --selftest
   python3 tools/gate.py
   ```
3. **Controls.**
   * *Positive*: the pre-fix ledger at `2e683be` with the new parser must name
     the dead rows — `--strict --claims /tmp/h100-pre.md` prints
     `RESERVED row names done/absent task: 288 rows over 63 tasks` and exits 1.
   * *Negative*: the same rule on a synthetic ledger where the owner is `open`
     must pass (the `--selftest` fixture, check `(s)`); a `done`, `blocked`,
     `open` and absent owner in one fixture must classify only `done`+absent as
     dead; a row carrying a note in the status or evidence cell (C-2538) is not
     a placeholder and is never touched.
   * *Unchanged control*: `--count-check` must stay `0` mismatches before and
     after the deletion.
4. **Scope.** `docs/research/claims.md`, `TODO.md`, `tools/claims_check.py`.
   The rule reads `TODO.md` through `todo_check` (one status parser, not a
   fork) and treats an unreadable board as "owner absent" rather than crashing.
   It does not judge `open`/`in progress`/`blocked` owners; a `done (negative
   …)` status retires its block because `_parse_status` returns `done` for it.
   Lines outside `| C-… |` rows and the `Supersedes`/`Superseded by` prose
   mentions are out of scope.
5. **Falsifier.** Stated above, before the result.

## Observations

- `--reserved-census --claims /tmp/h100-pre.md` (baseline ledger, new parser):
  `RESERVED placeholder rows: 326 (done 117, absent 171, open 7, in progress 0,
  blocked 31)`.
- `--strict --claims /tmp/h100-pre.md` exits 1 with
  `RESERVED row names done/absent task: 288 rows over 63 tasks`; the first ten
  task lines list the owner, reason and up to ten IDs (e.g.
  `RESERVED H101 (done): 2 rows C-4288 C-4289`,
  `RESERVED H26 (absent): 9 rows C-2761 … C-2769`).
- `.md`-wide scan for the 288 dead IDs found 75 mentions, all of them
  task-block `Claims:` headers in `TODO.md` or expository prose in EXP/retro
  records — zero `Supersedes:`/`Superseded by:` pointer rows name a deleted ID
  (a row-scoped scan over `| C-… |` lines returned `0`).
- The baseline ledger has 61 `Supersede`-carrying lines
  (`git show 2e683be:docs/research/claims.md | grep -cE 'Supersede'` prints
  `61`); the cleaned ledger prints 62 only because C-5972 quotes the word once,
  and the diff of those lines is exactly that one added row — no pointer line
  was deleted.
- Row count `grep -cE '^\| C-' docs/research/claims.md`: `2614` now, `2902` at
  `2e683be` (the exact 288 deleted).
- After deleting the 288 rows: `--reserved-census` prints
  `RESERVED placeholder rows: 38 (done 0, absent 0, open 7, in progress 0,
  blocked 31)`, `--strict` prints `RESERVED row names done/absent task: 0 rows
  over 0 tasks` and `claims_check: OK`, exit 0.
- `grep -c 'RESERVED (' docs/research/claims.md` prints `41`: the 38
  placeholder rows plus three literal `RESERVED (` mentions that are not bare
  placeholders — C-2538 (a real reservation with an evidence note), C-5719 (an
  `OBSERVED` row that opens with `RESERVED (` and carries a note) and C-5970
  (this task's own claim quoting the shape). The Done-when's grep is a coarse
  sentinel; the gate-visible count is `--reserved-census`, which counts only
  the bare shape.
- `--strict --count-check` prints `count mismatches: 0` after the deletion.
- The 38 retained rows belong to seven live tasks: M6.18 (`open`, 7),
  M9.12 (`blocked`, 9), M4.28 (7), M5.16 (5), M4.27 (4), M4.29 (4),
  H92 (`blocked`, 2).
- `--selftest` prints `claims_check selftest: OK (51 checks)`; check `(s)`
  covers the done/open/blocked/absent classification, the not-a-placeholder
  C-2538 shape, and the `_reserved_fail` truth table.
- `python3 tools/gate.py` prints `gate: 4 pass, 0 fail, 0 skip`.

## Interpretation

- **FACT:** a bare `RESERVED (<owner>).` row is now a gate-visible state;
  `--strict` (and `--reserved`) fail on a `done`/absent owner, naming the owner,
  the reason and the count.
- **FACT:** deleting 288 `done`/absent placeholder rows kept `--count-check` at
  `0` mismatches, and no pointer row referenced a deleted ID (the pointer lines
  are unchanged apart from this record's own citation).
- **OBSERVED:** two separate censuses disagree with the SE 2026-11-17 numbers
  (285 rows / 97 done / 34 blocked / 151 absent) because the ledger moved
  between that count and the claim: the tip at `2e683be` parses to
  326 placeholder rows over 70 owners (117 done, 171 absent, 31 blocked,
  7 open). Both counts are "as measured"; neither is typed by hand.
- **UNKNOWN:** whether the 38 retained rows will retire themselves — the rule
  will fail as soon as an owning task is marked `done`, which is the point.

## Conclusion

`tools/claims_check.py` gains `--reserved` (implied by `--strict`),
`--reserved-census` and `--claims PATH`; a bare `RESERVED (<owner>).` row whose
owner is `done` or absent from `TODO.md` now fails the standing gate with the
owner and count in the message. `docs/research/claims.md` loses the 288 dead
placeholder rows and keeps the 38 whose owners are live; no real claim ID was
renumbered and no numeric `Claims:` header changed. `--count-check` stays `0`,
`todo_check` stays `0 error(s)` and `gate.py` is `4 pass, 0 fail, 0 skip`.

## Overtaken by a later commit

- none

## Reproduction

```bash
python3 tools/claims_check.py --reserved-census    # expected: 38 (done 0, absent 0, open 7, blocked 31)
python3 tools/claims_check.py --strict              # expected: RESERVED row names done/absent task: 0 rows over 0 tasks
python3 tools/claims_check.py --selftest            # expected: claims_check selftest: OK (51 checks)
```

## Follow-ups

- [ ] The two censuses (retro 285 vs tip 326) are both truthful at their
  revisions; no task is needed, only the note that a count without its
  revision is not comparable.
- [ ] A future task that closes M6.18, M9.12, M4.27, M4.28, M4.29 or M5.16 will
  trip this gate until that block is used or deleted — that is the intended
  behaviour, not a defect to silence.
