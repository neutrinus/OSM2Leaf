# EXP-2026-11-21-H127: a red gate log names the failing rule

- **Status:** done (2026-11-21: re-ran the done-when — `tools/gate.py --selftest`
  OK (20 checks, 0 failed); a synthetic `MISSING C-2953 docs/format/absent-fixture.md`
  row survives the old 40-line cap and appears first under
  `--- claims_check output (failures) ---` with `genuine missing evidence paths: 1`
  and `claims_check: FAILED`; a task that loses `Claims` surfaces
  `ERROR TODO.md:1889 H127: missing required field(s): Claims` and
  `todo_check: FAILED` first under `--- todo_check output (failures) ---`; on a
  clean tree `python3 tools/gate.py` stays `4 pass, 0 fail, 0 skip` rc=0)
- **Date:** 2026-11-21
- **Sample:** none (tool-only task) — no vendor bytes are read or written; the
  subject is `tools/gate.py`'s FAIL-tail selection.
- **Tools:** `python3 3.15.0`; `tools/gate.py` (`_fail_tail`, `FAIL_HINTS`,
  `selftest`), `tools/claims_check.py`, `tools/todo_check.py`.
- **Claims:** C-6680
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a red `CI quality gate` log name the failing rule (the `MISSING`/`ERROR`
line) instead of hiding it behind 40 `NONRUN`/`NOEXP` warning rows, without
changing what any gate asserts or its exit code?

## Hypothesis

`tools/gate.py` printed `"\n".join(lines[-40:])` for every non-selftest gate.
`claims_check` output is ~500 lines, so the last 40 are `NONRUN`/`NOEXP`
warnings and the actual failing line (`MISSING C-2141 archive/us256.img`) is
cut off. A per-gate hint filter (mirroring the existing `selftest` special
case) that keeps the summary/hint lines before the cap, capped at a per-kind
limit, fixes it. **Falsifier:** a red claims_check run whose gate log still
contains no line naming the failing claim/path/rule.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/gate.py` (the FAIL tail loop, `SKIP_MARKERS`, the `selftest` case) |
| SHA-256 | n/a (text file) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/gate.py`, `tools/claims_check.py`, `tools/todo_check.py` |

## Method

1. **Sample and hash.** `tools/gate.py` at this commit; no vendor bytes.
2. **Commands.**

   ```bash
   # the new helper's own checks
   python3 tools/gate.py --selftest          # OK (20 checks), rc=0

   # end-to-end claims_check case: a temp ledger row citing an absent docs path
   cp docs/research/claims.md /tmp/claims.bak
   # edit one row's evidence to '; `docs/format/absent-fixture.md`'
   python3 tools/gate.py 2>&1 | sed -n '/claims_check output/,/todo_check/p'
   # expect '  MISSING C-2953 docs/format/absent-fixture.md' first, then FAILED
   cp /tmp/claims.bak docs/research/claims.md

   # end-to-end todo_check case: remove a task's Claims field
   cp TODO.md /tmp/todo.bak
   # delete the H127 '- Claims:' line
   python3 tools/gate.py 2>&1 | sed -n '/todo_check output/,/fn_audit/p'
   # expect '  ERROR TODO.md:1889 H127: missing required field(s): Claims' first
   cp /tmp/todo.bak TODO.md

   # clean tree stays green
   python3 tools/gate.py                    # 4 pass, 0 fail, 0 skip, rc=0
   ```

3. **Controls.**
   *Positive:* the synthetic `MISSING` row and the missing-`Claims` ERROR both
   appear before the 40-line cap; `gate.py --selftest` covers both.
   *Negative:* a gate with no hint table (`mystery_gate`) and a `claims_check`
   FAIL with no hint line both keep the blind 40-line tail, so an unknown
   failure is never hidden; a flood of hint lines is capped with an elision
   marker.
4. **Scope.** `tools/gate.py` only (`FAIL_HINTS`, `_fail_tail`, the FAIL tail
   loop, a per-gate wall-time line). No change to any gate's assertions or
   exit codes; full output remains available via `--json`/raw.
5. **Falsifier.** A red claims_check run whose gate log still names no failing
   claim/path/rule.

## Observations

`gate.py --selftest` (the five new checks):

```
ok   claims_check FAIL tail keeps MISSING before the 40-line cap
ok   todo_check FAIL tail keeps ERROR and FAILED
ok   unknown gate keeps the blind 40-line tail
ok   claims_check FAIL without a hint line keeps the tail
ok   hint flood is capped with an elision marker
gate selftest: OK (20 checks, 0 failed)
```

End-to-end (synthetic absent path):

```
--- claims_check output (failures) ---
duplicate claim IDs: 0
unregistered proposed claims: 0
genuine missing evidence paths: 1
  MISSING C-2953 docs/format/absent-fixture.md
  NOEXP C-1900 …
  …
claims_check: FAILED
```

End-to-end (task loses `Claims`):

```
--- todo_check output (failures) ---
  ERROR TODO.md:1889 H127: missing required field(s): Claims
todo_check: FAILED
  WARN  TODO.md:4568 M8.B3: …
  …
```

Clean tree:

```
$ python3 tools/gate.py
selftest      PASS
claims_check  PASS
todo_check    PASS
fn_audit      PASS
gate: 4 pass, 0 fail, 0 skip
rc=0
```

## Conclusion

`tools/gate.py` now selects a FAIL tail per gate instead of a blind 40-line
slice. `FAIL_HINTS` names the lines a red run needs for `claims_check`
(`MISSING`, `genuine missing evidence paths`, `duplicate claim IDs`,
`unregistered proposed claims`, `count mismatches`, `BAD`, `UNREG`, `NOEXP`,
`claims_check: FAILED`), `todo_check` (`ERROR`, `todo_check: FAILED`) and
`fn_audit` (`GAP`, `UNMAPPED`, `fn_audit: FAILED`); `_fail_tail` keeps up to
40 hint lines (elided with a marker beyond that) plus the last 40 non-hint
lines, and a gate with no hint table or no matching hint keeps the old blind
tail, so an unknown failure is not hidden. A per-gate wall-time line is
printed when a gate FAILs. No gate's assertions or exit codes change. All
Done-when conditions hold.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 tools/gate.py --selftest    # OK (20 checks)
python3 tools/gate.py               # 4 pass, 0 fail, 0 skip
```
