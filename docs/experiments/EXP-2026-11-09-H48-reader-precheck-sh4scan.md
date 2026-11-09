# EXP-2026-11-09-H48-reader-precheck-sh4scan: delegate reader_precheck scan primitive to sh4scan

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** none (tool-only task; no vendor bytes read or committed)
- **Tools:** `python3` (host), `tools/reader_precheck.py --selftest`, `tools/sh4scan.py --selftest`; stdlib only
- **Claims:** C-3410, C-3411
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `tools/reader_precheck.py` (M1.12, AGENTS rule 14) satisfy M3.19’s
done-when clause “M1.12 imports it rather than duplicating the scan” by
importing or delegating to `tools/sh4scan.py` for overlapping scan
functionality, without changing reader_precheck’s precheck verdicts or
real/synthetic pins?

## Hypothesis

Path (a): safe overlap exists in the LE halfword scan primitive used by
reader_precheck’s edge scan. Delegating that primitive to `sh4scan` (which
delegates to `sh4dis.halfwords_le`, the pinned LE convention) and importing
`sh4scan` in `reader_precheck.py` satisfies the clause while preserving
behavior. **Falsifier:** `reader_precheck.py --selftest` or
`sh4scan.py --selftest` fails, the required `sh4scan` import/assertion is
absent, or the delegated behavior changes scan results (synthetic or real
build-A pins).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` (synthetic selftests); real build-A pins run by `reader_precheck.py --selftest` when `archive/head256.img` is resolvable |
| SHA-256 | `n/a` for this integration; real-pin image identity is reported by `reader_precheck.py --selftest` output when present |
| Offset(s) / VA(s) | `n/a` |
| Tool / version | `python3`, stdlib |
| Repo tool | `tools/reader_precheck.py`, `tools/sh4scan.py`, `tools/sh4dis.py` |

## Method

1. **Sample and hash.** No vendor sample. Baseline precheck (before edit):
   `python3 tools/sh4scan.py --selftest` passed; `tools/reader_precheck.py`
   did not import/delegate to `sh4scan` (M3.19 blocker, TODO H48/M3.19).
2. **Commands.** Runnable as written from repo root/worktree:

```bash
# baseline / gates
python3 tools/sh4scan.py --selftest
python3 tools/reader_precheck.py --selftest

# H48 done-when (a): import/delegation present
python3 -c "import ast, pathlib; s=pathlib.Path('tools/reader_precheck.py').read_text(); assert 'sh4scan' in s; print('ok')"

# repo gates required by task
python3 tools/selftest.py
python3 tools/claims_check.py
python3 tools/todo_check.py
```

3. **Controls.** *Positive:* `sh4scan --selftest` passes (pins LE/halfword
   scan semantics M3.19/C-2535). `reader_precheck --selftest` synthetic
   checks pass and, when an image is found, real build-A pins pass unchanged
   (same pins as pre-integration behavior). The done-when assertion finds
   `sh4scan` in `reader_precheck.py`. *Negative/control against meaningless
   integration:* the overlap is documented as the LE halfword scan primitive
   (`_words` edge-scan primitive delegated to `sh4scan.halfword_array`,
   which wraps `sh4dis.halfwords_le`); reader_precheck’s higher-level
   section/xref/edge logic is not duplicated from sh4scan and not unsafely
   replaced. If behavior changed, synthetic/real pins fail.
4. **Scope.** Covered: `tools/reader_precheck.py` import/docstring and
   `_words` LE halfword primitive delegation; EXP/claims/TODO H48 and M3.19
   rule-15 status update in this PR. Excluded: replacing `point_walk_l3`
   section loading, `sh4xref` logic, edge classification semantics, or
   `sh4scan` pattern/tag/mask/stride/anchor subcommand behavior (no direct
   overlap in those reader_precheck verdict paths). No Ghidra/QEMU/vendor
   data; no B/C scan claims.
5. **Falsifier.** If `reader_precheck.py --selftest` or
   `sh4scan.py --selftest` regresses, the `sh4scan` token/assertion is
   missing, or real/synthetic pins change, the delegation is wrong; revert
   or take path (b) with an explicit board/TL amendment rationale.

## Observations

Baseline (pre-edit): `python3 tools/sh4scan.py --selftest` →
`sh4scan selftest: OK`. `tools/reader_precheck.py` contained no `sh4scan`
import/delegation (M3.19 blocker).

Changes:
- `tools/reader_precheck.py`: added `import sh4scan` (M3.19/H48) and
  module docstring note that M3.19’s `sh4scan` scan engine/LE halfword
  primitive is imported and delegated, satisfying M3.19’s M1.12-import
  done-when clause.
- `reader_precheck._words(blob)` now delegates to
  `sh4scan.halfword_array(blob)` (documented). `sh4scan.halfword_array`
  delegates to `sh4dis.halfwords_le` (pinned LE convention, M1.14/M3.19);
  behavior is equivalent to the prior local LE array construction.

Checks run (2026-11-09, worktree `/tmp/opencode/osm2leaf-tl/h48`):

```text
$ python3 tools/sh4scan.py --selftest
sh4scan selftest: OK

$ python3 -c "import ast, pathlib; s=pathlib.Path('tools/reader_precheck.py').read_text(); assert 'sh4scan' in s; print('ok')"
ok

$ python3 tools/reader_precheck.py --selftest
synthetic checks: PASS
real build-A pins (head256.img): PASS
```

(Real build-A pins ran because `reader_precheck.py --selftest` resolved an
available `archive/head256.img` via its default-image lookup; output above
is the tool’s reported result.)

## Interpretation

The H48 done-when path (a) is satisfied: `tools/reader_precheck.py` imports
and delegates to `tools/sh4scan.py` for the overlapping LE halfword scan
primitive used by its edge scan (`_words` → `sh4scan.halfword_array`), with
`sh4scan`/`reader_precheck` selftests passing and build-A pins unchanged.
This addresses M3.19’s done-when clause “M1.12 imports it rather than
duplicating the scan” without duplicating `sh4scan`’s scan engine and
without changing reader_precheck verdict logic.

Delegated overlap (documented): LE halfword array primitive for aligned
SH-4 scan bytes (`sh4scan.halfword_array` / `sh4dis.halfwords_le`). Not
delegated/replaced (no safe direct overlap in this task): `point_walk_l3`
section/census model, `sh4xref` pool/load/function-edge verdict logic, and
`sh4scan`’s `pattern`/`tags`/`mask-pair`/`stride`/`anchors` command scans
(reader_precheck does not perform those searches). M3.19 is set back to
`open` (rule 15 note, PR #170) for closure once this PR merges.
