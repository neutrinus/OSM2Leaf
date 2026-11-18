# EXP-2026-11-18-H92: H92's Precheck re-pointed at a defect that exists after H91

- **Status:** done
- **Date:** 2026-11-18
- **Sample:** `none (docs/tool task)` — `TODO.md`, `docs/research/claims.md`,
  `tools/todo_check.py` and `tools/fixtures/fn_match_eu_us_2011.json` at
  `origin/main` `a48bbf9`; one historical tree, `c6e5df3^`.
- **Tools:** python3 3.15.0; `tools/claims_check.py`, `tools/todo_check.py`,
  `git show`/`grep -c`, `python3 -c` one-liners.
- **Claims:** C-4155
- **Supersedes:** none
- **Superseded by:** none

## Question

H92's original `Precheck` quoted H87's `stays `12`` line as the live defect.
H91 merged on 2026-11-18 and fixed that line, so H92 must name a prose count
whose quoted number the post-H91 tree no longer prints (or show that the shape
is measurable at all) before it builds a guard.

## Hypothesis

The post-H91 board still has prose-count defects the gate cannot see, and at
least one `grep -c`/`python3 -c`-shaped count that a re-run can confirm. If
every prose count is unmeasurable or correct, H92 has nothing to guard and must
ship the allowlist plus a mutation case only (its `Stop:`).
**Falsifier:** every quoted prose count on `main` is either correct or has no
command to re-run (then the Precheck cannot point at a defect, only at the
unmeasurability).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (docs/tool task)`; claim ledger and TODO board |
| SHA-256 | `none (docs/tool task)` |
| Revision | `origin/main` `a48bbf9`; historical `c6e5df3^` (before H91) |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py`, `tools/todo_check.py` |

## Method

1. **Sample and hash.** The claim ledger (`2221` rows at `a48bbf9`) and the
   TODO board; one historical ledger at `c6e5df3^` for the witness the old
   Precheck used.
2. **Commands.** Run from the repo root; the historical tree is read with
   `git show <rev>:<path>`, never checked out.
   ```bash
   python3 tools/claims_check.py --strict --count-check | grep -E 'count mismatches|claims_check'
   grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'
   python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"
   grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'
   python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
   git show c6e5df3^:docs/research/claims.md | grep '^| C-4101' | grep -c 'stays `12`'
   git show c6e5df3^:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'
   grep -c 'stays `12`' docs/research/claims.md
   ```
3. **Controls.** *Positive*: the post-H91 tree must still carry a stale prose
   count (`C-3894`'s `176` against `228`). *Negative*: H91's `stays `12`` must
   be gone from `docs/research/claims.md` (`0`), so the re-point is measured at
   the fixed tree and not a re-quote of the old Precheck.
4. **Scope.** `TODO.md` H92 `Precheck`/`Falsifier`/`Scope`/`Hints` and
   `docs/research/claims.md` C-3894/C-3740 (read-only, not edited); no claim
   text is changed by this record.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

```
$ python3 tools/claims_check.py --strict --count-check | grep -E 'count mismatches|claims_check'
count mismatches: 0
claims_check: OK
$ grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'
1
$ python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"
228
$ grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'
1
$ python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
13 5
$ git show c6e5df3^:docs/research/claims.md | grep '^| C-4101' | grep -c 'stays `12`'
1
$ git show c6e5df3^:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'
15
$ grep -c 'stays `12`' docs/research/claims.md
0
```

## Interpretation

- **FACT:** the gate is green (`count mismatches: 0`) while C-3894's evidence
  row says `parse_tasks` returns `176` and the same call prints `228` on
  `a48bbf9`. That is the other direction: a quoted count the tree no longer
  prints.
- **FACT:** C-3740 quotes `13 5` next to a `python3 -c` command, and the
  command prints `13 5` today — a `prints N` shape the guard can re-run and
  confirm green. That is the positive measurement control.
- **FACT:** at `c6e5df3^` the ledger had one `stays `12`` line and the list
  printed `15`, the witness the old Precheck used; after H91 it prints `0`, so
  the old Precheck can no longer be the live defect.
- **IMPLICATION:** H92's guard covers one measurable real shape (`prints`) and
  three unmeasurable (`stays` with no command: C-927/C-1023/C-4171). The
  Precheck therefore states both: a stale `stays`-class count (C-3894) and a
  measurable `prints` count (C-3740), plus the historical witness.

## Conclusion

H92's Precheck is re-pointed to C-3894's `176` vs `228` (a stale prose count on
the post-H91 tree, invisible to `--count-check`) and to C-3740's `13 5`
(a `python3 -c` count the guard re-runs); the historical `c6e5df3^` witness is
kept as the reason the shape matters. H91's line is `0` in the ledger, so
nothing here copies the old Precheck.

## Reproduction

```bash
grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'   # 1
python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"  # 228
grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'      # 1
python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"  # 13 5
grep -c 'stays `12`' docs/research/claims.md                             # 0
```

## Follow-ups

- [ ] C-3894's stale `176` is a document defect H92 did not touch (its Scope
  is the tool). A record pass fixes the row or pins it to a revision.
- [ ] H92's guard stays off by default: wiring it into `tools/gate.py` needs
  the unmeasurable `stays` rows resolved or allowlisted.

## Corrections after navigator review

(empty until the navigator round returns)
