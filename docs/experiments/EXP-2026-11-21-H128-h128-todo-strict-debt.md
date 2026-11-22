# EXP-2026-11-21-H128: `todo_check --strict` has a committed debt baseline

- **Status:** done (2026-11-21: re-ran the done-when — `--strict --baseline
  tools/fixtures/todo_strict_baseline.json` exits 0 on `main` and prints
  `8 error(s) over 4 task(s) (baseline 8, new 0)`; a temp `TODO.md` with one
  extra firmware task missing `Stop` exits 1 and names `NEW M9.99|Stop`; a temp
  `TODO.md` where `M3.13` is completed prints `cleared: M3.13` and exits 0;
  `python3 tools/selftest.py --only todo_check` PASS (31 checks); the default
  `python3 tools/todo_check.py` still exits 0)
- **Date:** 2026-11-21
- **Sample:** none (tool-only task) — no vendor bytes are read or written; the
  subject is `tools/todo_check.py` and its committed baseline fixture.
- **Tools:** `python3 3.15.0`; `tools/todo_check.py` (`--baseline`,
  `--update-baseline`, `_error_key`, `_load_baseline`, `_write_baseline`),
  `tools/selftest.py`.
- **Claims:** C-6700
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the `--strict` rule-14 ERROR set (currently 8 ERROR over 4 tasks) be
recorded as a committed baseline keyed by `(task ID, missing field)` so "it
grew" becomes a command, without suppressing a WARN, relaxing the firmware
rule, or editing any open task's block?

## Hypothesis

`todo_check --strict` exits 1 with 8 ERROR over 4 tasks (`M1.38`, `M3.13`,
`M3.29`, `M8.C`) and nothing records what the count was, so each pass
re-derives it by memory. A committed `tools/fixtures/todo_strict_baseline.json`
listing each `(task ID, missing field)`, plus `--baseline PATH` (fail only on
ERRORs whose key is not baselined; a cleared entry prints `cleared:`) and
`--update-baseline PATH` (write the current keys, print `+`/`-` rows), turns
the debt into a measurable set. Keying by `(task ID, field)` — never line
number (H71/H80) — means a task that clears its field still matches, and a new
task missing a field fails on the first PR that adds it. **Falsifier:** after
this task a new firmware task with a missing `Precheck`/`Scope`/`Stop` still
exits 0 under `--strict --baseline`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/todo_check.py`, `tools/fixtures/todo_strict_baseline.json` |
| SHA-256 | n/a (text files) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/todo_check.py`, `tools/selftest.py` |

## Method

1. **Sample and hash.** The `tools/todo_check.py` change and the committed
   baseline; no vendor bytes.
2. **Commands.**

   ```bash
   # snapshot the current strict debt into the committed baseline
   python3 tools/todo_check.py --update-baseline tools/fixtures/todo_strict_baseline.json

   # Done-when 1: exits 0 on main, prints the counts
   python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json
   #   -> 8 error(s) over 4 task(s) (baseline 8, new 0), todo_check: OK, rc=0

   # Done-when 2: a temp TODO with an extra firmware task missing Stop -> rc=1
   cp TODO.md /tmp/todo.bak
   #   append: - [ ] **M9.99 — …** / Status: open / Precheck / Scope / Done when / Claims (no Stop)
   python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json /tmp/todo.bak
   #   -> NEW M9.99|Stop, new 1, todo_check: FAILED, rc=1

   # Done-when 3: mark M3.13 done -> its 3 keys clear, still rc=0
   python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json /tmp/todo-done.bak
   #   -> cleared: M3.13, new 0, todo_check: OK, rc=0

   # Done-when 4/5
   python3 tools/selftest.py --only todo_check        # PASS (31 checks)
   python3 tools/todo_check.py                        # default, rc=0
   ```

3. **Controls.**
   *Positive:* the committed baseline has exactly the 8 current keys;
   `--strict --baseline` on `main` exits 0 with `new 0`.
   *Negative:* a new firmware task missing `Stop` is `NEW M9.99|Stop` and
   exits 1 (the baseline is a ledger, not a waiver); a structural error
   (duplicate task ID) has no key and is never baselined, so it always fails.
4. **Scope.** `tools/todo_check.py` (`--baseline`, `--update-baseline`,
   `_error_key`, `_load_baseline`, `_write_baseline`, `main`) plus the
   committed `tools/fixtures/todo_strict_baseline.json`. No WARN suppressed,
   no firmware rule relaxed, no open task's block edited.
5. **Falsifier.** A new firmware task missing `Precheck`/`Scope`/`Stop` exits
   0 under `--strict --baseline`.

## Observations

Precheck (unchanged):

```
$ python3 tools/todo_check.py --strict >/tmp/tc.txt 2>&1; echo $?
1
$ grep -cE '^  ERROR' /tmp/tc.txt
8
$ grep -E '^  ERROR' /tmp/tc.txt | sed -E 's/.*TODO.md:[0-9]+ ([A-Z0-9.]+):.*/\1/' | sort -u
M1.38
M3.13
M3.29
M8.C
$ python3 tools/todo_check.py; echo $?
0
```

Baseline snapshot:

```
$ python3 tools/todo_check.py --update-baseline tools/fixtures/todo_strict_baseline.json
  + M1.38|Stop
  + M3.13|Precheck
  + M3.13|Scope
  + M3.13|Stop
  + M3.29|Precheck
  + M8.C|Precheck
  + M8.C|Scope
  + M8.C|Stop
baseline updated: 8 entries (8 added, 0 cleared) at ba503549…
```

Done-when 1 (clean main):

```
$ python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json
todo_check [strict+baseline]: 307 tasks, 8 error(s) over 4 task(s) (baseline 8, new 0), 181 warning(s); refs archived 55 / ghost 0 / blocked 27
todo_check: OK
rc=0
```

Done-when 2 (new firmware task missing Stop):

```
  NEW M9.99|Stop
todo_check [strict+baseline]: 308 tasks, 9 error(s) over 5 task(s) (baseline 8, new 1), 181 warning(s); …
todo_check: FAILED
rc=1
```

Done-when 3 (M3.13 completed):

```
  cleared: M3.13
  cleared: M3.13
  cleared: M3.13
todo_check [strict+baseline]: 307 tasks, 5 error(s) over 3 task(s) (baseline 8, new 0), …
todo_check: OK
rc=0
```

Done-when 4/5:

```
$ python3 tools/selftest.py --only todo_check
tool:todo_check  PASS  0.11s
selftest: OK
$ python3 tools/todo_check.py; echo $?
0
```

## Conclusion

`tools/todo_check.py` now carries a committed debt baseline for the `--strict`
rule-14 ERROR set, keyed by `(task ID, missing field)` (never line number).
`--update-baseline PATH` writes the current keys with the HEAD revision and
prints the `+`/`-` rows; `--strict --baseline PATH` fails only on ERRORs whose
key is new (structural errors, which have no key, always fail) and prints
`cleared: <task>` for baselined entries that resolved — so H53's progress shows
up as `cleared:` lines instead of a re-derived count. The summary carries
`ERROR n over m tasks (baseline k, new N)`. No WARN is suppressed, the firmware
rule is unchanged, and no open task's block is edited. All Done-when conditions
hold; the Falsifier (a new firmware task missing a field still fails) is
demonstrated by the `NEW M9.99|Stop` case.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json   # rc=0, new 0
python3 tools/selftest.py --only todo_check                                                  # PASS
python3 tools/todo_check.py                                                                 # default, rc=0
```
