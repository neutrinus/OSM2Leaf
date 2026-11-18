# EXP-2026-11-18-H92: `--prose-counts` — a claim quoting a count the tree no longer prints

- **Status:** blocked (the mode is complete and tested; the standing-gate half is H111, so H92's `Done when` is not met — see `Unblock`)
- **Date:** 2026-11-18
- **Sample:** `none (tool-only task)` — the claim ledger `docs/research/claims.md`
  at two revisions (below) and `tools/fixtures/fn_match_eu_us_2011.json`. No
  image, no vendor bytes.
- **Tools:** python3 3.15.0; `tools/claims_check.py` (`--selftest`,
  `--prose-counts`), `tools/gate.py`, `tools/selftest.py`, `tools/todo_check.py`
- **Claims:** C-4150–C-4159
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
| Revision: this branch | `HEAD` of `task/h92-count-guard` `eb0e75d`: ledger `2231` rows, `299` `RESERVED (` lines |

Every ledger number below names which of the two revisions it was measured at;
the fixture is the same `13 5` at both, and the tip row count is `2231` both
before and after this round (two rows were booked, none added).

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
census: rows 2231 prints ['C-3740', 'C-4156'] stays ['C-927', 'C-1023'] footer []
claims_check: OK
$ echo $?
0

$ grep -cE '^\| C-[0-9]+ ' docs/research/claims.md          # tip
2231
$ git show a48bbf9:docs/research/claims.md | grep -cE '^\| C-[0-9]+ '
2211
$ grep -c 'RESERVED (' docs/research/claims.md
299
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
$ python3 tools/claims_check.py --prose-counts > /tmp/opencode/h92red.txt; echo "exit=$?"
exit=1
$ grep -E 'stale prose|STALE' /tmp/opencode/h92red.txt
stale prose counts: 1
  STALE COUNT C-3740: claims 12, command prints 13 (8bc8fd91d408a87d318e950c690af4938f8d8992)

# positive control 2: `stays N` over a real command at `a48bbf9`
$ printf '%s\n' '| C-9999 | … stays `12` … at `a48bbf9`; `grep -c "\"eu_va\"" …` |' >> docs/research/claims.md
$ python3 tools/claims_check.py --prose-counts > /tmp/opencode/h92stays.txt; echo "exit=$?"
exit=1
$ grep -E 'STALE' /tmp/opencode/h92stays.txt
  STALE COUNT C-9999: claims 12, the quoted command prints 13 (a48bbf9)

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
- **FACT:** the tip ledger has two measurable `prints` shapes, one of them
  actually compared: C-3740 (`13 5`, correct) and C-4156 (its own cell has no
  revision, so the mode skips it — unmeasured). There are two unmeasurable
  `stays` rows (`C-927` `1,358,592`, `C-1023` `45`; no command, no cell
  selftest). C-4171's `stays `0xfdb6`` is a hex offset, not a count, and is
  not a shape at all. Two measurable shapes is under H92's `Stop:` threshold of
  three, so enforcement stays off and the wiring is H111.
- **FACT:** `--selftest` grows 28 → 43 checks, and the gate stays
  `4 pass, 0 fail, 0 skip`; a depth-1 clone prints the skip, never a false 0.
- **OBSERVED (defect left in place):** C-3894's evidence row says
  `parse_tasks` returns `176` while the tree prints `229` at `HEAD`
  `5630048` (`228` at `102fb69`). The guard does not
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
(`0` stale, census `rows 2231 prints ['C-3740', 'C-4156'] stays ['C-927', 'C-1023']
footer []`); the seeded C-3740 mutation and an injected `stays 12` both go red
with exit 1, `--strict` leaves the mode off (C-3894 still invisible), and the
standing gate is unchanged (`4 pass`). Enforcement is tracked as H111.

## Re-pointed Precheck

H92's original `Precheck` quoted H87's `stays `12`` line, which H91 (`c6e5df3`)
fixed. The post-H91 board still has a prose-count defect the gate cannot see
(C-3894, `176` vs `229`), two measurable `prints` shapes (C-3740 measured,
C-4156 unmeasured) and two unmeasurable `stays` rows:

```bash
python3 tools/claims_check.py --strict --count-check | grep -E 'count mismatches|claims_check'   # 0 / OK
grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'                         # 1
python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"   # 229 (228 at 102fb69; H111 is the 229th)
grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'                             # 1
python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"  # 13 5
git show c6e5df3^:docs/research/claims.md | grep '^| C-4101' | grep -c 'stays `12`'             # 1
git show c6e5df3^:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'  # 15
grep -c 'stays `12`' docs/research/claims.md                                                    # 1 (C-4150's own quotation of c6e5df3^)
```

The first pair is the stale prose count on the post-H91 tree (`176` vs `229`
at `HEAD` `5630048`; `228` at `102fb69`, because H111's own block is the 229th),
gate green; C-3740 is the measurable `prints` control; `c6e5df3^` is the
historical witness (H91 is `c6e5df3`, so `c6e5df3^` is its parent). The last
line is `1` and that one row is C-4150's own quotation of the pre-H91 defect —
no other row asserts `stays 12`, so nothing here copies the old Precheck.

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
  pinned to a command (C-4156 in the same task's claim block).
- [ ] C-3894's `176` vs `229` is a document defect for a record pass; H92's
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
   clean, and `299` (the tip) is `STALE … got 297 (a48bbf9)` — the
   working-tree-differs-from-rev control.
4. **Hex is not a count.** `PROSE_STAYS_RE` gained `(?![\dx])`; C-4171's
   `stays `0xfdb6`` produces no shape (selftest case `(q)`), and the census
   now lists `stays ['C-927', 'C-1023']` with C-4171 gone.
5. **The `$ echo $?` under a pipe.** Removed; the positive control now runs
   the command without a pipe and prints `exit=1` from `echo $?`.
6. **The unshipped census.** `census()` and `_print_census()` are shipped and
   `--prose-counts` prints the line, so the EXP quotes a command.
7. **Revision per number.** Sample is now a revision table (`a48bbf9` =
   `2211` rows / `297` `RESERVED (`, tip = `2231` / `299`); the shallow-clone
   block names the real scratch path and the command it ran.
8. **One EXP.** `EXP-2026-11-18-H92-precheck-repoint` is deleted; its content
   is the "Re-pointed Precheck" section and C-4155 appears in exactly one
   `Claims:` header. The Method heredoc is gone (the controls use `sed`/
   `printf` plus `git checkout --`); `claims.md`'s C-4150 block reads one
   record ("the pre-H91 revision"); the Precheck follow-up points at H111.
9. **The wiring is a task, not a bullet.** TODO H111 (open, `Pair: required`,
   `Depends: H92, H78, H90`, Done when, Falsifier, Claims C-4460–C-4469)
   carries it; C-4156 records the obligation. H92 is `Status: blocked` with
   `Unblock: H111`: the code is complete but the standing-gate half is not, so
   the `Done when` (a green gate with the rule standing) is not met.

Non-blocking: the unused `PROSE_SHELL_CHARS` is gone and the logic lives in
`_shell_operators` (docstring says `True`, not `or None`); the `stays`-via-
selftest branch is documented in the docstring (a tool's footer may pin a list
its selftest builds — H87's `US_BUILD_STARTS`; a footer is a different number,
so it is only used when the cell has no allowlisted command); the
first-token-only limitation is in "Rejected shapes".

Verified after the changes: `--selftest` 43 checks, `--strict --count-check`
OK, `--prose-counts` 0 stale, gate `4 pass`, `todo_check` 229 tasks 0 errors.

### Round 3 (navigator: all 9 code items verified fixed; 6 record defects + verdict)

The code was accepted; the remaining defects are in this record, the ledger and
the board. All are applied here.

1. **C-4155's `228`.** `len(todo_check.parse_tasks(...))` prints `229` at
   `HEAD` `5630048` (`228` at `102fb69`, the 229th block being H111's own).
   The claim now says `229` at `HEAD` and names `102fb69` for the `228`.
2. **C-4155's `stays `12`` is `0`.** False: `grep -c 'stays `12`'
   docs/research/claims.md` prints `1`, and that row is C-4150's own quotation
   of `c6e5df3^`. The claim, this record (Precheck block and the sentence under
   it) and TODO H92's Precheck all say `1` and name C-4150 as the quoting row;
   no other row asserts `stays 12`.
3. **The census in TODO.** H92's `Result` line and H111's `Precheck` quoted
   a stale census (`rows 2231 prints ['C-3740']`, and earlier `2233`); the
   command prints `rows 2231 prints ['C-3740', 'C-4156']`. H111 is fixed
   (H92's line was removed by item 7), and both say "two measurable `prints`
   shapes (C-3740 measured, C-4156 unmeasured)".
4. **The `2231` claim.** `HEAD` printed `2233` while this round's ledger work
   was in flight; after the two new rows were booked inside H92's own id block
   (item 6) the tip prints `2231` again. C-4157 and the Sample table now say
   `2231` at `HEAD`, measured after the rename.
5. **The positive controls under a pipe.** The `$ echo $?` after a pipeline
   printed `0`, not the tool's exit. Both now write to a file and read `$?`
   from the tool (`> /tmp/opencode/h92red.txt; echo "exit=$?"` prints `1`),
   then `grep` the file for the `STALE` line.
6. **H92's `Claims:` range.** It reaches past its own block: C-4160–C-4169 is
   M1.32's (on `main`), so `todo_check` flagged `overlapping claim ranges
   C-4150-4161 (H92) and C-4160-4169 (M1.32)`. The two rows are filed as
   C-4156/C-4157 inside H92's own C-4150–C-4159 (both reserved and unused on
   every branch, `git grep -c` prints nothing), the header stays
   `C-4150–C-4159`, and nothing is taken from another task.
7. **Verdict.** H92 is `Status: blocked`, `[ ]` still unticked, with
   `Blocker:` (the mode is off by default, so no standing gate fails on the
   H87 class) and `Unblock: H111`; the Result line is removed (it claimed a
   done H92 does not have) and this record's `Status` is `blocked`. The
   positive and negative controls stay recorded above: they prove the mode
   works, which is the part that is complete.
8. **H111's claim block.** `Claims: C-4460–C-4469` collided with M5.45; the
   TL's `chore/tl-15-parallel-sessions` branch allocates C-4480–C-4579 to
   M3.27/M4.42–M4.45/M5.47/M7.6/M9.46/M9.47, so the next free block is
   C-4580–C-4589 (`git grep -c 'C-4580' <every origin branch>` prints nothing).
   H111 now carries it; C-4156 no longer names a range.
