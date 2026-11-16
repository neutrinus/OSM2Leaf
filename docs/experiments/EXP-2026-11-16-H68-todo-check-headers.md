# EXP-2026-11-16-H68-todo-check-headers: an unparsed block header must be an error

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** none (tool-only task) — the evidence is `tools/todo_check.py`
  run against `TODO.md`; `TODO.md` is a text board, not vendor data, so no
  binary sample hash applies. The board revision is pinned by the commit that
  carries this EXP.
- **Tools:** `python3` 3.13, `tools/todo_check.py`, `tools/worktree_audit.py`,
  `tools/progress_report.py`, `tools/selftest.py`, `tools/claims_check.py`
- **Claims:** C-3890, C-3891, C-3892, C-3893, C-3894, C-3895, C-3896, C-3897
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `todo_check.py` report a block header it cannot parse, or does it fold
that header into the previous block and go green?

## Hypothesis

`TASK_RE` rejects a dual-ID header (`**A / B — …**`, `**A, B — …**`), a
bold-only header (`**H1**`) and a markdown-heading header
(`### **H1 — …**`); because `parse_tasks` only starts a block on a `TASK_RE`
match, such a line is appended to the previous task's body and `check()`
returns `ok: True` with no warning. **Falsifier:** any of those headers makes
`check()` return a nonzero task count *and* no error, or the current board
already produces the error.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at the H68 branch tip |
| Shape count | `grep -cE '^- \[[ xX]\] \*\*' TODO.md` |
| Parser | `tools/todo_check.py` (`TASK_RE`, `parse_tasks`, `check`, `run_selftest`) |
| Fallback consumer | `tools/worktree_audit.py:188` (`import todo_check`, `parse_tasks`) |
| Bounded lookup | `tools/progress_report.py:265` (`parse_todo_tasks`) |

## Method

1. **Sample and hash.** No binary sample; `TODO.md` is the sample. The exact
   `TODO.md` and `tools/todo_check.py` are the files under test, pinned by the
   commit that carries this EXP.
2. **Commands.** Runnable as written:

   ```bash
   # precheck: dual-ID header is absorbed (0 tasks parsed)
   python3 -c "import sys;sys.path.insert(0,'tools');import todo_check as t;print(len(t.parse_tasks('- [ ] **H2 / H3 — x**\n  - Status: open\n')))"

   # the four negatives + one positive, all inside the tool's own selftest
   python3 tools/todo_check.py --selftest

   # positive board control: 0 errors, exit 0, no unparsed-header error
   python3 tools/todo_check.py

   # a temp copy with one real block rewritten as a dual-ID header exits 1
   python3 - <<'PY'
   import tempfile, pathlib
   src = pathlib.Path('TODO.md').read_text().splitlines()
   i = next(i for i, l in enumerate(src) if l.startswith('- [ ] **H68 —'))
   src[i] = '- [ ] **H999 / H998 — x**'
   p = pathlib.Path(tempfile.mkdtemp()) / 'TODO.md'
   p.write_text('\n'.join(src) + '\n')
   print(p)  # then: python3 tools/todo_check.py <p>
   PY

   # consumer still parses the real board
   python3 -c "import sys;sys.path.insert(0,'tools');import todo_check as t;from pathlib import Path;print(len(t.parse_tasks(Path('TODO.md').read_text())))"
   python3 tools/selftest.py --only todo_check
   python3 tools/selftest.py --only worktree_audit
   python3 tools/claims_check.py
   ```

3. **Controls.** *Positive:* the live `TODO.md` must still exit 0 with 0
   errors and parse every real block; a well-formed single header
   `**H1 — t**` must still parse as one task; non-bold section headings
   (`## H — Housekeeping`, `### ID allocation`) must not error. *Negative:*
   each of the four malformed headers must produce
   `block header not parsed by TASK_RE` and exit 1.
4. **Scope.** `tools/todo_check.py` only; `TODO.md` as read-only input. The
   counted corpus is every `^- \[[ xX]\] \*\*`-shaped line in `TODO.md`
   (177 lines: 176 parsed blocks plus 1 fenced template example at line 176),
   plus the synthetic fixtures in `run_selftest`. `progress_report.py` is
   read only (checked for the same hole, not modified).
5. **Falsifier.** A dual-ID/comma/bold-only/heading header that parses into a
   task with no error, or a current board that reports an unparsed-header
   error, refutes the hypothesis.

## Observations

Precheck, before the change:

```text
$ python3 -c "import sys;...;print(len(t.parse_tasks('- [ ] **H2 / H3 — x**\n  - Status: open\n')))"
0
```

`check()` on a two-block doc (`**H1 —**` then `**H2 / H3 —**`) returned
`tasks == 1`, `ok == True` before the change; the `H2 / H3` header was folded
into H1's body.

After the change:

```text
$ python3 tools/todo_check.py --selftest
todo_check selftest: OK (18 checks, 176 real tasks)

$ python3 tools/todo_check.py
todo_check: 176 tasks, 0 error(s), 150 warning(s)
```

Temp copy with H68 rewritten as `**H999 / H998 — x**`:

```text
exit 1
  ERROR TODO.md:694: block header not parsed by TASK_RE: - [ ] **H999 / H998 — x**
```

Board shape count and parse count:

```text
$ grep -cE '^- \[[ xX]\] \*\*' TODO.md
177
$ python3 -c "import todo_check as t; ... print(len(t.parse_tasks(...)))"
176
```

Consumers:

```text
$ python3 tools/selftest.py --only todo_check      -> passed=1 failed=0
$ python3 tools/selftest.py --only worktree_audit  -> passed=1 failed=0
$ python3 tools/claims_check.py                    -> claims_check: OK
```

`progress_report.parse_todo_tasks` on a doc with `**H1 —**` + `**H2 / H3 —**`
and IDs `[H1, H2, H3]` returned `['H1','H2']` and the problem
`task H3 not found`. It searches `^- \[…\] \*\*<known-id>` per requested ID, so
it neither absorbs the dual header nor invents a task; it reports H3 missing.

## Interpretation

- **FACT:** a `^- \[[ xX]\] \*\*` line, or a `### **…` bold heading, that
  `TASK_RE` rejects is now a default-on error
  (`block header not parsed by TASK_RE`), so it fails the gate instead of
  being absorbed.
- **FACT:** the four malformed forms (`/`, `,`, no-dash bold-only, `###`
  heading) each fail the selftest with that error; the well-formed single
  header and non-bold section headings pass.
- **FACT:** the live board still exits 0 with 0 errors; the corrupt temp copy
  exits 1 naming line 694 and the header.
- **OBSERVED:** the counted corpus is 177 shaped lines, 176 parsed; the one
  unparsed line is the fenced template example, which `_unparsed_headers`
  skips because fenced blocks are excluded, same as `parse_tasks`.
- **OBSERVED:** `worktree_audit` reuses `todo_check.parse_tasks` and still sees
  the whole board (176 tasks); its selftest passes.
- **OBSERVED:** `progress_report.parse_todo_tasks` has the same family of hole
  but a different shape — a bounded per-ID lookup that reports `task … not
  found` rather than absorbing the header. Left unchanged (out of H68 scope;
  its failure is loud, not silent).
- **HYPOTHESIS:** none. The change is a guard, not a model of the format.
- **UNKNOWN:** whether a future form (e.g. `**A & B —**`) should be split
  rather than rejected; H68 deliberately keeps every dual-ID header illegal
  because a real dual block carries one `Claims` range that cannot be split
  without the author (PO split `M8.D1 / M8.D2` by hand).

## Conclusion

`tools/todo_check.py` now treats a header-shaped line it cannot parse as a
hard error, in both the checkbox and bold-heading shapes, default-on. Dual-ID
headers stay illegal on purpose (decision recorded: flag and let the author
split, never guess-split), so a `/`- or `,`-joined, bold-only or heading-style
header fails loudly instead of vanishing into the previous block. The same
parser is reused by `worktree_audit`; no second TODO parser was added. The
live board is unchanged: 176 tasks, 0 errors, exit 0.

## Reproduction

```bash
python3 tools/todo_check.py --selftest     # expected: OK (18 checks, 176 real tasks)
python3 tools/todo_check.py                # expected: 176 tasks, 0 error(s), exit 0
```

## Follow-ups

- [ ] H60 (same parser, different failure class) can build on
  `_unparsed_headers` when it classifies archived/ghost/blocked `Depends`.
- [ ] `progress_report.parse_todo_tasks` shares the bounded-lookup hole; its
  failure is loud (`task … not found`), so it is noted, not changed here.
