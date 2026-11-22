# EXP-2026-11-21-H94: H90's EXP is re-runnable as written (counts from commands, one clone block)

- **Status:** done (2026-11-21: re-ran the done-when — `grep -cE '809 commits|5x|3\.15|five .main. pushes'`
  on the EXP now returns only lines that cite the command that printed them
  (`git rev-list --count` → 108, `git count-objects -vH` → 19.74 MiB, `git
  --version` → 2.56.0, `python3 -V` → 3.15.0) and the two remaining `809`/
  `2.5x`/`3.15` hits are explicitly labelled H90's own quoted strings, not
  retyped measurements; the clone recipe is one `( cd "$X" && … )` block; and
  H90's Done-when (b)–(d) still pass: `claims_check --selftest` OK (51
  checks), `gate.py` 4 pass/0 fail/0 skip, `claims_check --strict --count-check`
  OK, `todo_check.py` OK)
- **Date:** 2026-11-21
- **Sample:** none (tool-only task) — no vendor bytes are read or written; the
  subject is `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md`.
- **Tools:** `python3 3.15.0`, `git 2.56.0`; `tools/claims_check.py`,
  `tools/gate.py`, `git rev-list --count`, `git count-objects -vH`.
- **Claims:** C-4200
- **Supersedes:** none (repairs H90's EXP; H93 owns the navigator section)
- **Superseded by:** none

## Question

Can H90's EXP be made re-runnable as written — every number quoted from a
command that prints it, the clone recipe one copy-pasteable block, and the
failed-run count consistent with the twelve red pushes C-4130 states — without
changing any claim or the H93 navigator section?

## Hypothesis

Three EXP defects survive H90/H93: (1) the Sample's `809 commits, pack 3.2
MiB` and the Tools' `git 2.5x, python3 3.15` are typed, not from a command;
(2) the Method command block lists `git clone … && cd /tmp/x` then a second
`git fetch --unshallow` line that would run in the wrong cwd; (3) the Method's
"five `main` pushes whose run failed" contradicts the twelve red pushes the
Question/Inputs already state. Each can be fixed in the EXP text alone.

**Falsifier:** the typed `809 commits`/`2.5x`/`3.15` strings remain as
uncited measurements, or the clone recipe is still two lines that leave the
subshell cwd, or the run count is still "five".

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` |
| SHA-256 | n/a (text file) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 -V` → `Python 3.15.0`; `git --version` → `git version 2.56.0` |
| Repo tool | `git rev-list --count`, `git count-objects -vH`, `tools/claims_check.py` |

## Method

1. **Sample and hash.** The H90 EXP text; no vendor bytes.
2. **Commands.**

   ```bash
   # what the EXP now quotes for its own numbers
   git rev-list --count 3d79bcc                 # 108 (H94's own repo)
   git count-objects -vH | grep size-pack       # size-pack: 19.74 MiB
   git --version                                # git version 2.56.0
   python3 -V                                   # Python 3.15.0

   # the Done-when grep: 0, or each hit cites its command
   grep -cE '809 commits|5x|3\.15|five .main. pushes' \
     docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md

   # H90's Done-when (b)-(d) still pass
   python3 tools/claims_check.py --selftest             # OK (51 checks)
   python3 tools/gate.py                                # 4 pass, 0 fail, 0 skip
   python3 tools/claims_check.py --strict --count-check # OK
   python3 tools/todo_check.py                          # OK
   ```

3. **Controls.**
   *Positive:* `git rev-list --count 3d79bcc`, `git count-objects -vH`,
   `git --version`, `python3 -V` each print the number the EXP now quotes.
   *Negative:* the Done-when grep must not return an **uncited** typed count —
   every surviving hit must sit next to the command that printed it (H90's own
   quoted strings are labelled as such, not as measurements).
4. **Scope.** `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` only
   (Sample, Tools, Inputs, Method step 1/2). No claim rows; H93 owns the
   navigator/Corrections section. `tools/` untouched.
5. **Falsifier.** The typed strings remain uncited, or the recipe is still two
   lines, or the run count is still "five".

## Observations

The four numbers the EXP quotes, each from its command:

```
$ git rev-list --count 3d79bcc
108
$ git count-objects -vH | grep size-pack
size-pack: 19.74 MiB
$ git --version
git version 2.56.0
$ python3 -V
Python 3.15.0
```

Done-when grep (surviving hits, all cited):

```
8:  `size-pack: 19.74 MiB`. H90's original block quoted `809 commits, pack
12:  prints `git version 2.56.0`, `python3 -V` prints `Python 3.15.0`; repo tools
14:  original block listed `git 2.5x, python3 3.15` as its own environment; that
46:| Tool / version | `python3 -V` → `Python 3.15.0`, `git --version` → `git version 2.56.0` (H94's own measurement, 2026-11-21; H90's `3.15`/`2.5x` quoted as H90's environment) |
```

Lines 8 and 14 are H90's own quoted strings (labelled as such, with H90's
measurement pinned by C-4135), not retyped counts; lines 12 and 46 cite
`python3 -V` / `git --version` directly. No `five` remains (the Method now
says twelve, `1889340..2b3d1b4`, matching C-4130).

The collapsed clone recipe (Method step 2):

```bash
X=$(mktemp -d); R=$PWD
git clone --depth 1 file://$R "$X" && ( cd "$X" && \
  python3 tools/claims_check.py --strict --count-check; \
  git fetch -q --unshallow "$R" && \
  python3 tools/claims_check.py --strict --count-check )
```

H90's Done-when (b)–(d) re-run in H94's environment:

```
$ python3 tools/claims_check.py --selftest | tail -1
claims_check selftest: OK (51 checks)
$ python3 tools/gate.py | tail -1
gate: 4 pass, 0 fail, 0 skip
$ python3 tools/claims_check.py --strict --count-check | grep claims_check:
claims_check: OK
$ python3 tools/todo_check.py | tail -1
todo_check: OK
```

## Conclusion

All three EXP defects are text-only and fixed in place: the Sample/Tools now
quote `git rev-list --count` (108), `git count-objects -vH` (19.74 MiB),
`git --version` (2.56.0) and `python3 -V` (3.15.0) as H94's own measurements,
while H90's `809`/`2.5x`/`3.15` remain labelled as H90's quoted strings (pinned
by C-4135), never retyped as measurements; the clone recipe is one
`( cd "$X" && … )` block so the second command runs in the clone's cwd; and
the failed-run count is twelve (`1889340..2b3d1b4`), matching C-4130. H90's
Done-when (b)–(d) still pass, and no claim row or the H93 navigator section is
touched. All Done-when conditions hold.

## Reproduce

```bash
git clone <repo> && cd <repo>
git rev-list --count 3d79bcc && git count-objects -vH | grep size-pack
grep -cE '809 commits|5x|3\.15|five .main. pushes' \
  docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md
python3 tools/gate.py   # 4 pass, 0 fail, 0 skip
```
