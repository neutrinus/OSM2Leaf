# EXP-2026-11-20-H60: `todo_check` tells a ghost `Depends` from an archived one

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `none (tool-only task)`; the board `TODO.md` at `434a2949`
  (297 tasks) and the ten frozen archives `docs/research/todo-history-*.md`.
- **Tools:** python3 3.15.0; `tools/todo_check.py`, `tools/selftest.py`,
  `tools/gate.py`
- **Claims:** C-3800–C-3809
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `todo_check` say whether an unresolved `Depends`/`Unblock` ID is a Ghost
on the board, a block the PO archived to `todo-history-*.md`, or a live block
that is `blocked`, instead of one `references unknown task ID` line for all
three?

## Hypothesis

Yes: every frozen archive is a `[x]` block header with the board's own task-ID
shape, so an ID seen there is archived; an ID seen nowhere is a ghost; an ID
on a live `blocked` block is blocked. **Falsifier:** a real archived ID is
still reported as ghost, or the classification makes a fresh checkout (no
archive) exit non-zero.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at `434a2949`, 297 task blocks |
| Archives | `docs/research/todo-history-2026-11-0{5,6,9,13,15,16,17,18,19,20}.md` |
| Tool | `tools/todo_check.py` (`check`, `_parse_depends`, `parse_tasks`) |

## Method

1. **Sample.** The board and the ten archives named above.
2. **Commands.**
   ```bash
   python3 tools/todo_check.py                      # summary line + WARN lines
   python3 tools/todo_check.py --json | head -40     # dep_classes counters
   python3 tools/todo_check.py --selftest            # 24 checks
   python3 tools/selftest.py --only todo_check
   python3 tools/gate.py
   ```
3. **Controls.** *Positive*: with the archives read, the board's archived refs
   are `archived task ID '…'`, none of them error. *Negative 1*:
   a temp board with an empty `history_dir` reports the same archived ID as
   `unknown task ID` and still exits 0 (a fresh checkout must not false-fail).
   *Negative 2*: against the real archive set, a probe block that depends on a
   real archived ID is `archived`, and with that ID changed to `H9999` it is
   `ghost`.
4. **Scope.** `tools/todo_check.py` only, plus the one real ghost the new
   dialog exposed (H43's `Depends: … M9 …` → explicit `M9.2/M9.14/M9.17/
   M9.18/M9.24`). `--strict`'s verdict set is H53's and is not changed: the
   same 12 firmware-field `ERROR` lines remain.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

`origin/main`'s pre-H60 tool on the board at `434a2949`:

```
todo_check: 297 tasks, 0 error(s), 155 warning(s)
unknown-ref lines: 41
exit 0
```

`tools/todo_check.py --json` on the new tool (same board, the real
`docs/research/` archives):

```
"dep_classes": {"archived": 42, "ghost": 0, "blocked": 27}
"archived_ids": 174
```

The one ghost the split found before the board fix:

```
WARN  TODO.md:1909 H43: Depends references ghost task ID 'M9'
```

(H43's line read `Depends: … M9.12 and runnable M9 reader targets`; `M9` is
not a task, it is a stream name used as prose. Fixed to the five real reader
targets.)

Selftest: `todo_check selftest: OK (24 checks, 297 real tasks)`;
`selftest.py --only todo_check` `passed=1 failed=0 skipped=0`;
`--strict`'s `ERROR` lines now number 9 (the firmware-field set shrank on
`main` as the other agents landed fields; the rule is H53''s and H60 does not
change it).

## Interpretation

- **FACT:** the archive split recognises 174 archived IDs and classifies the
  board's 42 archived references without a single error.
- **FACT:** a board with no archive degrades to the old `unknown task ID`
  wording and exits 0.
- **FACT:** the real archive set classifies an archived probe as `archived` and
  the same ID changed to `H9999` as `ghost`.
- **OBSERVED:** 27 board references (Depends and Unblock) point at a live
  `blocked` block; those are now labelled `blocked`, not lost among ghosts.
- **UNKNOWN:** whether H53's `--strict` will promote a ghost to an error; this
  task leaves the switch alone and records the hook H53 must wire.

## Conclusion

`todo_check` now prints `refs archived N / ghost M / blocked K` (a `Depends`
or an `Unblock` reference alike) and a per-line class, so a PO archive can no longer hide a ghost among normal
archived references. The board's only ghost (`H43 → M9`) is named and fixed;
the 9 `--strict` firmware-field errors are H53's and unchanged. Claims
C-3800–C-3809.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/todo_check.py --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["dep_classes"])'
python3 tools/todo_check.py --selftest
```

## Follow-ups

- [ ] H53: wire a ghost reference into `--strict` as an error once the
  firmware-field errors are cleared.
