# EXP-2026-11-18-H92: `--prose-counts` — a claim quoting a count the tree no longer prints

- **Status:** done
- **Date:** 2026-11-18
- **Sample:** `none (tool-only task)` — the claim ledger `docs/research/claims.md`
  at two revisions (below) and `tools/fixtures/fn_match_eu_us_2011.json`. No
  image, no vendor bytes.
- **Tools:** python3 3.15.0; `tools/claims_check.py` (`--selftest`,
  `--prose-counts`), `tools/gate.py`, `tools/selftest.py`, `tools/todo_check.py`
- **Claims:** C-4150–C-4161
- **Supersedes:** `EXP-2026-11-18-H92-precheck-repoint` (its re-point section
  is folded in here as "Re-pointed Precheck"; that draft file is removed)
- **Superseded by:** none

## Question

`claims_check --count-check` fails only when a claim's *selftest* count matches
the wrong tool revision. Can a mode catch the other direction — a claim quoting
any other count the tree no longer prints — without guessing at prose?

## Hypothesis

The safe shapes are few and mechanical: a `grep -c`/`python3 -c` command the
cell already quotes followed by `prints N`, a `stays N` next to such a command,
and the exact selftest footer `OK (N checks`. Re-running only those, only when
H78 gives the claim a measurement revision, and at *that* revision, turns
H87's defect red without a false positive on a legitimate `N at <sha>`.
**Falsifier:** a seeded stale `stays 12` over a command that prints 15 is not
`STALE COUNT` with exit 1, or a correct `N at <sha>` row goes red.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (tool-only task)`; the claim ledger, one checked-in fixture |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | none |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (`--prose-counts`, `--selftest`) |
| Revision: branch base | `origin/main` `a48bbf9`: ledger `2211` rows, `297` `RESERVED (` lines |
| Revision: this branch | `HEAD` of `task/h92-count-guard`: ledger `2233` rows, `301` `RESERVED (` lines |

Every ledger number below names which of the two revisions it was measured at;
the fixture is the same `13 5` at both.

## Method

1. **Sample and hash.** The claim ledger at the branch base (`a48bbf9`) and at
   the branch tip; the checked-in fixture. The census is a shipped line
   (`census: rows … prints … stays … footer …`), not a pasted script.
2. **Commands.** Run from the repo root; the mutation blocks restore the file
   with `git checkout --` afterwards.
   ```bash
   python3 tools/claims_check.py --prose-counts
   python3 tools/claims_check.py --prose-counts --json
   python3 tools/claims_check.py --selftest
   python3 tools/gate.py
   grep -cE '^\| C-[0-9]+ ' docs/research/claims.md
   git show a48bbf9:docs/research/claims.md | grep -cE '^\| C-[0-9]+ '
   grep -c 'RESERVED (' docs/research/claims.md
   git show a48bbf9:docs/research/claims.md | grep -c 'RESERVED ('
   grep -c '"eu_va"' tools/fixtures/fn_match_eu_us_2011.json
   python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
   python3 tools/claims_check.py --help | grep -A2 prose
   # the failed-command control (not a zero):
   python3 -c "import sys; sys.path.insert(0,'tools'); import claims_check as cc; print(cc._run_prose_command('grep -c x tools/h92-no-such-file.txt'))"
   # the hex control (C-4171's offset is not a count):
   python3 -c "import sys; sys.path.insert(0,'tools'); import claims_check as cc; print(cc.PROSE_STAYS_RE.findall('stays \`0xfdb6\`'))"
   # positive control: a stale printed count -> red
   sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
   python3 tools/claims_check.py --prose-counts; echo "exit=$?"
   git checkout -- docs/research/claims.md
   # positive control: the `stays N` shape over a real command at a real revision
   printf '%s\n' '| C-9999 | The fixture stays `12` rows. | VERIFIED (tool) | H | EXP-2026-11-18-H92-count-guard; at `a48bbf9`; `grep -c "\"eu_va\"" tools/fixtures/fn_match_eu_us_2011.json` |' >> docs/research/claims.md
   python3 tools/claims_check.py --prose-counts; echo "exit=$?"
   git checkout -- docs/research/claims.md
   # negative control: the mode is off under --strict (the gap is unchanged)
   python3 tools/claims_check.py --strict --count-check | grep -c 'STALE'
   ```
3. **Controls.** *Positive 1*: C-3740 seeded `13 5` → `12 5` must be `STALE
   COUNT` with exit 1. *Positive 2*: the injected `stays 12` row next to a
   `grep -c` that prints `13` must be `STALE COUNT` with exit 1. *Negative 1*:
   the unmodified ledger must print `stale prose counts: 0`, exit 0.
   *Negative 2*: `--strict --count-check` must print no `STALE` line (the mode
   is off, so the C-3894 defect is still invisible — the gap H111 tracks).
   *Negative 3*: `grep -c` over a missing path must be `None` (skipped), not
   `0`; a hex `stays `0xfdb6`` must produce no shape.
4. **Scope.** `tools/claims_check.py` only: the `--prose-counts` flag, three
   regex shapes, the `grep -c`/`python3 -c` allowlist, a `git archive`
   re-runner and the census line. Excluded: every other claim row (read, never
   edited), every EXP `Observations` block and task `Result` (not parsed —
   "Rejected shapes"), and enforcement in `tools/gate.py` (H111).
5. **Falsifier.** Stated in the Hypothesis, before the result.

## Observations

```
$ python3 tools/claims_check.py --selftest
claims_check selftest: OK (43 checks)          # was 28 before H92

$ python3 tools/claims_check.py --prose-counts
...
stale prose counts: 0
census: rows 2233 prints ['C-3740', 'C-4160'] stays ['C-927', 'C-1023'] footer []
claims_check: OK
$ echo $?
0

$ grep -cE '^\| C-[0-9]+ ' docs/research/claims.md          # tip
2233
$ git show a48bbf9:docs/research/claims.md | grep -cE '^\| C-[0-9]+ '
2211
$ grep -c 'RESERVED (' docs/research/claims.md
301
$ git show a48bbf9:docs/research/claims.md | grep -c 'RESERVED ('
297
$ grep -c '"eu_va"' tools/fixtures/fn_match_eu_us_2011.json
13
$ python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
13 5

$ python3 -c "... cc._run_prose_command('grep -c x tools/h92-no-such-file.txt')"
None
$ python3 -c "... cc.PROSE_STAYS_RE.findall('stays `0xfdb6`')"
[]

# positive control 1: seeded stale printed count
$ sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
$ python3 tools/claims_check.py --prose-counts | grep -E 'stale prose|STALE'
stale prose counts: 1
  STALE COUNT C-3740: claims 12, command prints 13 (8bc8fd91d408a87d318e950c690af4938f8d8992)
$ echo $?
1

# positive control 2: `stays N` over a real command at `a48bbf9`
$ printf '%s\n' '| C-9999 | … stays `12` … at `a48bbf9`; `grep -c "\"eu_va\"" …` |' >> docs/research/claims.md
$ python3 tools/claims_check.py --prose-counts | grep -E 'STALE'
  STALE COUNT C-9999: claims 12, the quoted command prints 13 (a48bbf9)
$ echo $?
1

# negative control: the mode is off under --strict
$ python3 tools/claims_check.py --strict --count-check | grep -c 'STALE'
0
$ python3 tools/claims_check.py --strict --count-check | tail -1
claims_check: OK

# a shallow checkout says so instead of a false 0
$ git clone --depth 1 file://$PWD ~/projekty/leafre-work/scratch/h92/shallow
$ (cd ~/projekty/leafre-work/scratch/h92/shallow && python3 tools/claims_check.py --prose-counts | tail -2)
prose count check: skipped (shallow clone; fetch the full history to run it)
claims_check: OK

$ python3 tools/gate.py | tail -1
gate: 4 pass, 0 fail, 0 skip
$ python3 tools/selftest.py | tail -2
passed=93 failed=0 skipped=23 total=116 time=48.5s
selftest: OK
$ python3 tools/todo_check.py | head -1
todo_check: 229 tasks, 0 error(s), 161 warning(s)
```

## Interpretation

- **FACT:** the guard turns a seeded stale printed count red with exit 1
  (C-3740 `12` against a command that prints `13`) and the `stays` shape over a
  real command red with exit 1 (C-9999 `12` against `13` at `a48bbf9`); the
  unmodified ledger is `stale prose counts: 0`, exit 0.
- **FACT:** the tip ledger has one measurable printed count actually compared
  (`C-3740`, correct `13 5`; C-4160's own cell mentions the flag name but has
  no `grep -c` command, so its `prints` shape is unmeasurable) and two and two unmeasurable `stays` rows (`C-927` `1,358,592`, `C-1023`
  `45`; no command, no cell selftest). C-4171's `stays `0xfdb6`` is a hex
  offset, not a count, and is not a shape at all. Two measurable shapes is
  under H92's `Stop:` threshold of three, so enforcement stays off and the
  wiring is H111.
- **FACT:** `--selftest` grows 28 → 43 checks, and the gate stays
  `4 pass, 0 fail, 0 skip`; a depth-1 clone prints the skip, never a false 0.
- **OBSERVED (defect left in place):** C-3894's evidence row says
  `parse_tasks` returns `176` while the tree prints `228`. The guard does not
  see it — the row quotes `176` as prose after a backticked tool name, no
  `grep -c`/`python3 -c`, no footer — which is the "do not parse arbitrary
  prose" line. Named in the Re-pointed Precheck, fixed by a record pass (H111
  dependency), not here.
- **REJECTED shapes** (not re-run, by design): a `Result:` line or an EXP
  `Observations` block (append-only records, not the ledger); a `prints N`
  whose command is not `grep -c`/`python3 -c`; any command with an `archive/…`
  input (a vendor fetch is not a gate's price); any command with an unquoted
  shell operator (`|`, `>`, `;`, `$(…)`) — the text is ledger prose, so it runs
  as a `shlex` argv, never through a shell; a git-ignored fixture that is not
  in the `git archive` of a pinned revision (skipped, not measured against the
  working tree); a bare `stays N` with no command or selftest (C-927/C-1023 —
  unmeasurable, skipped). `_run_prose_command` reads only the **first** stdout
  token: a `python3 -c` that prints `13 5` (C-3740) is compared on `13` and its
  `5` is never re-run, so C-3740's UNIQUE half is unguarded.
- **LIMITATION:** the mode is not in `tools/gate.py` (H111).

## Conclusion

`tools/claims_check.py --prose-counts` adds the other direction of the count
rule: three mechanical shapes re-run only through an allowlist, only when
H78's measurement revision exists, and at that revision; a non-zero command
exit is skipped rather than read as `0`. On the current ledger it is green
(`0` stale, census `rows 2233 prints ['C-3740', 'C-4160'] stays ['C-927', 'C-1023']
footer []`); the seeded C-3740 mutation and an injected `stays 12` both go red
with exit 1, `--strict` leaves the mode off (C-3894 still invisible), and the
standing gate is unchanged (`4 pass`). Enforcement is tracked as H111.

## Re-pointed Precheck

H92's original `Precheck` quoted H87's `stays `12`` line, which H91 (`c6e5df3`)
fixed. The post-H91 board still has a prose-count defect the gate cannot see,
and one measurable printed count:

```bash
python3 tools/claims_check.py --strict --count-check | grep -E 'count mismatches|claims_check'   # 0 / OK
grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'                         # 1
python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"   # 228
grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'                             # 1
python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"  # 13 5
git show c6e5df3^:docs/research/claims.md | grep '^| C-4101' | grep -c 'stays `12`'             # 1
git show c6e5df3^:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'  # 15
grep -c 'stays `12`' docs/research/claims.md                                                    # 0
```

The first pair is the stale prose count on the post-H91 tree (`176` vs `228`,
gate green); C-3740 is the measurable `prints` control; `c6e5df3^` is the
historical witness (H91 is `c6e5df3`, so `c6e5df3^` is its parent). The last
line is `0`, so nothing here copies the old Precheck.

## Reproduction

```bash
python3 tools/claims_check.py --selftest           # claims_check selftest: OK (43 checks)
python3 tools/claims_check.py --prose-counts       # census ... ; stale prose counts: 0 ; exit 0
sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
python3 tools/claims_check.py --prose-counts; echo "exit=$?"   # STALE COUNT C-3740 ... exit=1
git checkout -- docs/research/claims.md
python3 tools/gate.py                              # gate: 4 pass, 0 fail, 0 skip
```

## Follow-ups

- [ ] H111 wires `--prose-counts` into `tools/gate.py` after C-927/C-1023 are
  pinned to a command (C-4160 in the same task's claim block).
- [ ] C-3894's `176` vs `228` is a document defect for a record pass; H92's
  guard deliberately does not parse that prose shape.
- [ ] Only the first stdout token is compared: a command printing `N M` leaves
  `M` unguarded (C-3740's `5`). Widening it needs a per-shape expectation.

## Corrections after navigator review

The navigator returned 9 blocking items plus 3 non-blocking ones; all are
applied in this round.

1. **C-4150's revision.** `f5a989` was not an object (`git cat-file -t` →
   fatal). The claim now cites `c6e5df3^` (`c6e5df3` is H91's merge, verified
   with `git log --oneline -- docs/research/claims.md`) and keeps H91's
   `stays `12`` count as the witness.
2. **A failed command is not `0`.** `_run_prose_command` returns `None` unless
   the process exits `0` (`grep`'s exit `1` — no match — is the one allowed
   non-zero, since it prints `0`); the selftest asserts a missing path is
   `None`, not `0`.
3. **`prints N` is measured at the row's revision.** `_run_prose_command(cmd,
   rev)` extracts `tools/`, `docs/`, `TODO.md` and `.gitignore` from the
   commit with `git archive` (the `_run_selftest` pattern) and runs there; a
   git-ignored fixture absent from the archive is skipped, not measured at
   HEAD. Selftest case `(r)`: a row pinning `297` `RESERVED (` at `a48bbf9` is
   clean, and `301` (the tip) is `STALE … got 297 (a48bbf9)` — the
   working-tree-differs-from-rev control.
4. **Hex is not a count.** `PROSE_STAYS_RE` gained `(?![\dx])`; C-4171's
   `stays `0xfdb6`` produces no shape (selftest case `(q)`), and the census
   now lists `stays ['C-927', 'C-1023']` with C-4171 gone.
5. **The `$ echo $?` under a pipe.** Removed; the positive control now runs
   the command without a pipe and prints `exit=1` from `echo $?`.
6. **The unshipped census.** `census()` and `_print_census()` are shipped and
   `--prose-counts` prints the line, so the EXP quotes a command.
7. **Revision per number.** Sample is now a revision table (`a48bbf9` =
   `2211` rows / `297` `RESERVED (`, tip = `2233` / `301`); the shallow-clone
   block names the real scratch path and the command it ran.
8. **One EXP.** `EXP-2026-11-18-H92-precheck-repoint` is deleted; its content
   is the "Re-pointed Precheck" section and C-4155 appears in exactly one
   `Claims:` header. The Method heredoc is gone (the controls use `sed`/
   `printf` plus `git checkout --`); `claims.md`'s C-4150 block reads one
   record ("the pre-H91 revision"); the Precheck follow-up points at H111.
9. **The wiring is a task, not a bullet.** TODO H111 (open, `Pair: required`,
   `Depends: H92, H78, H90`, Done when, Falsifier, Claims C-4460–C-4469)
   carries it; C-4160 records the obligation. H92 stays `in progress` with no
   `Unblock:` (it is not blocked — the mode works and is deliberately opt-in).

Non-blocking: the unused `PROSE_SHELL_CHARS` is gone and the logic lives in
`_shell_operators` (docstring says `True`, not `or None`); the `stays`-via-
selftest branch is documented in the docstring (a tool's footer may pin a list
its selftest builds — H87's `US_BUILD_STARTS`; a footer is a different number,
so it is only used when the cell has no allowlisted command); the
first-token-only limitation is in "Rejected shapes".

Verified after the changes: `--selftest` 43 checks, `--strict --count-check`
OK, `--prose-counts` 0 stale, gate `4 pass`, `todo_check` 229 tasks 0 errors.
