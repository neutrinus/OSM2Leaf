# EXP-2026-11-21-H99: workflows README names the one `tools/gate.py` step, not the pre-H85 three

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** `none (tool-only task)` — the change is documentation
  (`.github/workflows/README.md`); no vendor bytes are read.
- **Tools:** python3 3.13 (`gate.py` runs `selftest.py`, `claims_check.py`,
  `todo_check.py`, `fn_audit.py`); repo tools `tools/gate.py`,
  `tools/todo_check.py`, `tools/claims_check.py`
- **Claims:** C-4270–C-4274
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `.github/workflows/README.md` describe the gate CI actually runs, so a
new agent reading it learns the one `tools/gate.py` step, the four gates
inside it, and the SKIP-is-never-PASS policy — instead of three separate
commands `ci.yml` no longer runs as three steps?

## Hypothesis

The README's "Hard gate" list is pre-H85 prose (three commands). Rewriting it
to the one `tools/gate.py` step, with a four-row gate table matching
`gate.py`'s own `Gate(...)` names and the SKIP rule, makes the contract match
`ci.yml`. **Falsifier:** the README still lists `selftest.py --json` and
`claims_check.py` as separate hard-gate steps, or it names a gate
`tools/gate.py` does not run.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `.github/workflows/README.md`, `.github/workflows/ci.yml`, `tools/gate.py` |
| SHA-256 | none (tool-only task) — repo text files |
| Offset(s) / VA(s) | — |
| Tool / version | python3 3.13 |
| Repo tool | `tools/gate.py` (the source of the four gate names) |

## Method

1. **Sample and hash.** No vendor sample; the inputs are the committed text
   files above (the task is documentation only). Recorded as
   `none (tool-only task)` per TEMPLATE.
2. **Commands.**
   ```bash
   # precheck: the pre-fix state
   grep -n 'selftest.py --json\|claims_check.py`\|todo_check.py TODO.md\|### Hard gate' .github/workflows/README.md
   grep -n 'tools/gate.py' .github/workflows/README.md | grep -v unchanged
   # the gate names gate.py actually runs
   grep -n 'Gate("' tools/gate.py
   # after the rewrite
   grep -n 'tools/gate.py' .github/workflows/README.md
   grep -n 'selftest.py --json\|claims_check.py` —\|todo_check.py TODO.md`' .github/workflows/README.md; echo "rc=$?"
   # the standing gate and the board/claims checks
   python3 tools/gate.py
   python3 tools/todo_check.py
   python3 tools/claims_check.py --strict --count-check
   ```
3. **Controls.** *Positive*: `grep -n 'Gate("' tools/gate.py` lists exactly
   the four names the README table uses (`selftest`, `claims_check`,
   `todo_check`, `fn_audit`), so the table can be checked against the tool.
   *Negative*: the pre-fix `sed`/`grep` shows the three old commands present;
   after the rewrite the same `grep` for the old list exits 1 (no match) — a
   rewrite that left the old list would print a match and fail the control.
4. **Scope.** `.github/workflows/README.md` only (the "Hard gate" block and
   its four-row table + SKIP paragraph). The `main-watch.yml` section (H117)
   and the informational Python 3.14 paragraph are unchanged; `H86` owns the
   `l1l2-fixtures.yml` policy text and is not touched here. No workflow logic
   is changed (`ci.yml` already runs `tools/gate.py`).
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Pre-fix (the defect): the "Hard gate" list carried the three pre-H85 commands,
and `tools/gate.py` appeared only as the H117 "unchanged" note (line 20), not
as a gate step:

```
26:### Hard gate (blocking merge check)
30:- `python tools/selftest.py --json` — repo/tool selftests. …
31:- `python tools/claims_check.py` — `docs/research/claims.md` ledger consistency.
32:- `python tools/todo_check.py TODO.md` — `TODO.md` board structure/claim-allocation lint (H24). …
```

`tools/gate.py` Gate names (`grep -n 'Gate("' tools/gate.py`):

```
166:        Gate("selftest", [PY, "tools/selftest.py"]),
167:        Gate("claims_check", claims),
168:        Gate("todo_check", todo),
169:        Gate("fn_audit", fn_audit, optional_input=image),
```

Post-fix (Done-when):

```
$ grep -n 'tools/gate.py' .github/workflows/README.md
20:RUNS_JSON` run the same policy offline. `tools/gate.py` is unchanged.
30:- `python tools/gate.py` — the standing gate (H85). It runs four commands in a fixed order and applies one **PASS / FAIL / SKIP** policy:
$ grep -n 'selftest.py --json\|claims_check.py` —\|todo_check.py TODO.md`' .github/workflows/README.md; echo "rc=$?"
rc=1
```

The rewritten table (`grep -n` of the four gate rows):

```
34:  | `selftest` | `python tools/selftest.py` |
35:  | `claims_check` | `python tools/claims_check.py --strict --count-check` |
36:  | `todo_check` | `python tools/todo_check.py` (strict on under `--board-clean`, red until H53) |
37:  | `fn_audit` | `python tools/fn_audit.py archive/head256.img --corpus … --overlay …` |
39:- **SKIP is never PASS.** …
40:- `fn_audit` is the gate that **SKIPs in PR CI**: `archive/head256.img` is not on the runner. It must **PASS** in H84's manual IMG256 job, …
```

Board and ledger after the rewrite:

```
$ python3 tools/todo_check.py
todo_check: 297 tasks, 0 error(s), 156 warning(s)
todo_check: OK
```

```
$ python3 tools/claims_check.py --strict --count-check
RESERVED row names done/absent task: 0 rows over 0 tasks
claims_check: OK
```

Standing gate (`python3 tools/gate.py`, image present on this host):

```
GATE          RESULT    SECS  NOTE
------------  ------  ------  ----------------------------------------
selftest      PASS    117.13
claims_check  PASS      6.69
todo_check    PASS      0.06
fn_audit      PASS      4.21
gate: 4 pass, 0 fail, 0 skip
```

## Interpretation

- **FACT:** Before the rewrite the "Hard gate" list named
  `python tools/selftest.py --json`, `python tools/claims_check.py` and
  `python tools/todo_check.py TODO.md` as three separate stats; no gate step
  named `tools/gate.py`.
- **FACT:** After the rewrite `grep -n 'tools/gate.py'` prints the gate step
  (line 30) and the old three-command list no longer matches (`rc=1`).
- **FACT:** The four README table rows use exactly the `Gate(...)` names
  `tools/gate.py` prints (`selftest`, `claims_check`, `todo_check`,
  `fn_audit`), so the table is checkable against the tool, not prose.
- **OBSERVED:** The README now says a SKIP is listed in the job summary and
  never counted as PASS, and that `fn_audit` is the gate that SKIPs in PR CI
  (no head) and must PASS in H84's manual job.
- **HYPOTHESIS:** none.
- **UNKNOWN:** none — this is documentation, fully checked by the Done-when
  greps.

## Conclusion

`.github/workflows/README.md` now describes the one `tools/gate.py` step that
`ci.yml` actually runs, with a four-row gate table (`selftest`,
`claims_check --strict --count-check`, `todo_check`, `fn_audit`), the
SKIP-is-never-PASS rule, and the line that `fn_audit` SKIPs in PR CI but must
PASS in H84's manual job. The pre-H85 three-command list is gone. No format
knowledge and no workflow logic changed. `python3 tools/todo_check.py` is OK,
`claims_check --strict --count-check` is OK, and `python3 tools/gate.py` is
`4 pass, 0 fail, 0 skip`.

## Overtaken by a later commit

- `todo_check: 278 tasks, 0 error(s), 162 warning(s)` (first local run) and the
  gate timings `114.91 / 5.46 / 0.05 / 4.09` | no later commit changed a file
  this record cites; `origin/main` simply advanced while the branch was being
  prepared (`git fetch origin && git log -1 origin/main` → `434a2949`) | the
  post-rebase run reads `todo_check: 297 tasks, 0 error(s), 156 warning(s)` and
  `gate: 4 pass, 0 fail, 0 skip` (timings `117.13 / 6.69 / 0.06 / 4.21`); no
  H99 claim changed meaning (`python3 tools/todo_check.py`; `python3 tools/gate.py`)

## Reproduction

```bash
grep -n 'tools/gate.py' .github/workflows/README.md                 # line 30 is the gate step
grep -c 'selftest.py --json' .github/workflows/README.md            # 0
python3 tools/todo_check.py                                         # todo_check: OK
python3 tools/gate.py                                               # 4 pass, 0 fail, 0 skip (image present)
```

## Follow-ups

- [ ] H86 (open, separate PR) owns the `l1l2-fixtures.yml` policy text and the
      negative-CI proof; this rewrite does not touch that section.
