# EXP-2026-11-22-H83: board-ref lint

- **Status:** done
- **Date:** 2026-11-22
- **Sample:** `none (tool-only task)` — the sample is `TODO.md` itself, a
  versioned repository file, not vendor bytes; no image is read.
- **Tools:** `python3 3.15.0`; `tools/todo_check.py` (this branch), `tools/gate.py`,
  `tools/selftest.py`; `git` for the frozen revisions below.
- **Claims:** C-4060–C-4069
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the two mechanical classes of board-prose rot in the *Priorities* section —
a bold task ID that resolves to no block, and a task the prose calls next / in
flight / a current blocker while its status is `done` or archived — become a
warning on the board and an error under `--strict`, without rewriting any prose
and without turning the default gate red?

## Hypothesis

`tools/todo_check.py` already parses every block (`parse_tasks`, fence-aware).
A second pass over only the first `## Priorities` section, reusing that parse,
can classify bold-ID mentions into: `unresolved` (no live block, archive entry
or live-block parent), `not_next` (a `done`/archived ID under a
`next`/`then`/`Take first`/`in flight` verb on the same bullet) and `drift` (a
`done`/archived ID under `blocked on`/`only after`/`cannot be taken until`,
warning-only). The rule is **strict-only in effect**: warnings by default, errors
only under `--strict`, so `tools/gate.py` (which runs the default) stays green
until H53's strict pass / `--board-clean` adopts it. The findings are
**structural** (no `_error_key`), so H128's `--baseline` can never absorb them.

**Falsifier (stated before the result):** a fixture Priorities line naming a
`done` task as `next` is not flagged under `--strict` (or does not warn by
default); a history sentence (`merged **ID**`) is flagged; a correct parent
(`M8.C1` → `M8.C1b`), an archived ID, or a re-opened live ID is reported
unresolved/stale; or `tools/gate.py` goes red on the default board.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at this branch (`bd92ec6a`, rebased on `origin/main` `17b22eaf`), 323 parsed blocks |
| Frozen retro | `TODO.md` at `6504090b` (2026-11-16), `6803705a` (2026-11-16) |
| Tool | `tools/todo_check.py` (`_board_refs`, `_ref_resolves`, `check(... strict_board_refs=...)`) |
| Standing gate | `tools/gate.py` (default `todo_check`) |

## Method

1. **Sample and hash.** `TODO.md` is a versioned file; its identity is the
   revision `bd92ec6a` (this branch, rebased on `origin/main` `17b22eaf`). No
   hash is pinned because the board moves
   on every merge; every count below names the revision it was measured at.
2. **Commands.** Runnable as written:

```bash
# today's board, default (warnings only) and the row printer
python3 tools/todo_check.py
python3 tools/todo_check.py --board-refs
# the same board under --strict: the four not-next rows become ERRORs
python3 tools/todo_check.py --strict
# the tool's own fixtures (falsifier cases as asserts)
python3 tools/todo_check.py --selftest
# the standing gate must stay green (default todo_check)
python3 tools/gate.py
# a historical board, read through the new lint (frozen revision)
git show 6504090b:TODO.md > /tmp/opencode/h83-6504090b.md
git show 6803705a:TODO.md > /tmp/opencode/h83-6803705a.md
python3 tools/todo_check.py /tmp/opencode/h83-6504090b.md --board-refs
python3 tools/todo_check.py /tmp/opencode/h83-6803705a.md --board-refs
```

3. **Controls.** *Positive*: today's board has four live stale refs
   (L342 `next **H105**`, L344 `in flight **M9.58**/**M9.60**/**M9.61**`, all
   `done`) and they are reported. The frozen `6803705a` board reports one real
   stale `next **M1.23**` (`done`). *Negative*: a history sentence
   (`Cycle 8 merged **H2**`), a `(ready …)` context mention, the range base
   `M8.C1` (children `M8.C1b`/`M8.C1c` live), an archived ID and a re-opened
   live ID are all clean — asserted in `--selftest` (80 checks). *Baseline*: on
   `--baseline tools/fixtures/todo_strict_baseline.json` the summary prints
   `new 0` and the four board-ref refs are counted but not baselined.
4. **Scope.** The first `## Priorities` section only (line 267 to the next
   `^## ` heading, line 369). A second `## Priorities` (the stale 21st-pass copy
   at line 604) is one `sections` warning, not scanned, so its stale refs do not
   flood the report. `Depends:`/`Unblock:` fields are untouched (H125 owns
   `Unblock`, so class (3) is Priorities prose only and never double-reports).
   Prose is never rewritten.
5. **Falsifier.** As stated in Hypothesis.

## Observations

Measured at `bd92ec6a` (rebased on `origin/main` `17b22eaf`) unless a revision is named.

- **Today, default:** `todo_check: 323 tasks, 0 error(s), 207 warning(s)`;
  summary tail `board-refs unresolved 0 / not-next 4 / drift 0 / sections 1`,
  exit 0 — measured at `bd92ec6a` (rebased on `origin/main` `17b22eaf`). Before
  H83 the same board produced **0** reported stale refs (no gate saw the
  prose); the contribution is **5** warnings (4 `not_next` + 1 `sections`). The
  pre-rebase head `d2dc9c0a` had 321 blocks and the same `0/4/0/1` split; the
  merge that rebased this branch (M8.C1d/M8.C1e) added two blocks, not refs.
- **Today, `--board-refs` rows:**

```text
TODO.md:342 / Priorities / not_next / H105 / done
TODO.md:344 / Priorities / not_next / M9.58 / done
TODO.md:344 / Priorities / not_next / M9.60 / done
TODO.md:344 / Priorities / not_next / M9.61 / done
board-refs: unresolved 0 / not-next 4 / drift 0 / sections 1
```

- **Today, `--strict`:** exit 1, `22` ERROR lines total (H53's rule-14
  backlog), of which **4** are the board-ref `not_next` rows above; the
  `sections` warning stays a warning (measured at `bd92ec6a`).
- **Baseline (H128):** `--baseline tools/fixtures/todo_strict_baseline.json`
  prints `8 error(s) over 4 task(s) (baseline 8, new 0)`, `todo_check: OK`; the
  board-ref refs are in the summary but never in the ledger (`_error_key` is
  `None` for them, asserted in `--selftest`).
- **Frozen `6504090b` (2026-11-16):** `unresolved 0 / not-next 0 / drift 0 /
  sections 0` **after** the live-beats-archive fix below. Before that fix it
  printed `not-next 2` at L233/L249 (`next **M1.27**`), a false positive:
  `M1.27` is `open` at that revision but a `done` row for it exists in today's
  `todo-history-2026-11-17.md`.
- **Frozen `6803705a` (2026-11-16):** `TODO.md:247 / Priorities / not_next /
  M1.23 / done` — a real stale `next` the old board carried.
- **Selftest:** `todo_check selftest: OK (80 checks, 323 real tasks)`.
- **Standing gate:** `gate: 5 pass, 0 fail, 0 skip` (`todo_check PASS`).
- **`selftest.py`:** `passed=184 failed=0 skipped=21 total=205`, `selftest: OK`.

## Interpretation

- **FACT:** the lint catches the four live stale refs and the frozen
  `6803705a` `next M1.23`, and leaves history, `(ready …)` context, the
  `M8.C1` range base, archived IDs and re-opened live IDs alone (`--selftest`).
- **FACT:** default output is warnings only; `--strict` promotes `unresolved`
  and `not_next` to errors and keeps `drift`/`sections` warnings. The default
  gate stays `PASS`.
- **OBSERVED (design):** `ready` and `blocked on` are deliberately *not* class-2
  verbs. L342 `L1 (ready …)` names the done `H105` as context and L345
  `M8.D1 is blocked on Marek` is about a person; including them would cry wolf.
  `in flight` **is** class 2, which is what catches L344.
- **UNKNOWN / board defect, not fixed here:** the second `## Priorities`
  (21st pass, line 604) is a stale duplicate of the whole section; the lint
  names it once (`sections 1`) and the PO owns its removal. Likewise L342's
  `next **H105**` and L344's in-flight list are real prose the PO edits on the
  report — this task does not rewrite them.

## Conclusion

`tools/todo_check.py` gained a `--board-refs` mode (on by default as warnings,
errors under `--strict`) over the first Priorities section. On today's board it
reports `unresolved 0 / not-next 4 / drift 0 / sections 1` and exits 0; under
`--strict` the four `not_next` rows are errors. Findings are structural and
never baselined. The value is under `--board-clean`/after H53; the default gate
is green by design. Claims C-4060–C-4069.

## Overtaken by a later commit

none (record written at the task's own merge).

## Reproduction

```bash
python3 tools/todo_check.py --board-refs    # expected: unresolved 0 / not-next 4 / drift 0 / sections 1
python3 tools/todo_check.py --selftest      # expected: OK (80 checks, 323 real tasks)
python3 tools/gate.py                       # expected: 5 pass, 0 fail, 0 skip
```

## Follow-ups

- [ ] PO: remove the stale second `## Priorities` (21st pass) and refresh L342
      `next H105` / L344 in-flight list — reported by `--board-refs`, not fixed
      here (Scope: tool only).
