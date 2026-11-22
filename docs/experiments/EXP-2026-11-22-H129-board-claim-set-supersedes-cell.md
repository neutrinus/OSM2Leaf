# EXP-2026-11-22-H129-board-claim-set-supersedes-cell

- **Status:** done
- **Date:** 2026-11-22
- **Sample:** none (tool-only task) — edits `tools/board.py` and the live claim row C-6750; no vendor image required.
- **Tools:** `python3 3.13.1`, repo tools `tools/board.py`, `tools/claims_check.py`, `tools/gate.py`, `tools/selftest.py`
- **Claims:** C-6760, C-6761, C-6762, C-6763
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `board.py claim-set` place `Supersedes:` in the claim body (cell 2) when the key is absent, and does its selftest detect a regression that writes it to evidence (cell 5)?

## Hypothesis

`op_claim_set` currently scans body then evidence and, when no existing key is found, appends `; Key: Value` to evidence cell 5. That matches the C-6750 specimen before this fix and causes a second `claim-set` call to be a no-op only by coincidence of the key already being present in evidence. The fix is to insert a missing key into body cell 2, while preserving in-place replacement in body or evidence. Falsifier: after the fix, `claim-set` on a row with no `Supersedes` leaves `Supersedes` absent from cell 2 or present in cell 5, or the selftest still passes when the field lands in cell 5.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only task) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.13.1` |
| Repo tool | `tools/board.py`, `tools/claims_check.py`, `tools/gate.py` |

## Method

1. **Sample and hash.** No vendor sample; the live specimen is `docs/research/claims.md` row `C-6750` on `origin/main` (commit `17b22eaf` at worktree base, rebased onto `origin/main` before edits). Before fix: `Supersedes` present in body cell 2, absent in evidence cell 5.
2. **Commands.**

```bash
cd /home/marek/projekty/OSM2Leaf.task-h129-claim-set-supersedes
# before: show C-6750 cell placement
python3 - <<'PY'
import re, pathlib
for l in pathlib.Path('docs/research/claims.md').read_text().splitlines():
    if l.startswith('| C-6750 |'):
        parts=re.split(r'(?<!\\)\|', l)
        print('BEFORE|cells',len(parts),'|sup_body', 'Supersedes' in parts[2], '|sup_evid', 'Supersedes' in parts[5])
        print('BODY_TAIL', parts[2][-80:])
        print('EVID_TAIL', parts[5][-80:])
PY

# fix implemented in tools/board.py: op_claim_set inserts missing key into cell 2;
# Supersedes matches legacy `Supersedes C-nnnn` (no colon). Selftest asserts
# body/evidence cell placement and legacy rewrite.

python3 tools/board.py --selftest

# apply the task's required command on the live ledger
python3 tools/board.py claim-set C-6750 Supersedes C-6460

# after: show C-6750 cell placement
python3 - <<'PY'
import re, pathlib
for l in pathlib.Path('docs/research/claims.md').read_text().splitlines():
    if l.startswith('| C-6750 |'):
        parts=re.split(r'(?<!\\)\|', l)
        print('AFTER|cells',len(parts),'|sup_body', 'Supersedes' in parts[2], '|sup_evid', 'Supersedes' in parts[5])
        print('BODY_TAIL', parts[2][-80:])
        print('EVID_TAIL', parts[5][-80:])
PY

python3 tools/claims_check.py --strict --count-check
python3 tools/gate.py
```

3. **Controls.** Positive: `board.py --selftest` contains a case that adds `Supersedes` to a row with no such key and asserts it lands in cell 2 and not cell 5; it also replaces an existing `Supersedes` and rewrites legacy `Supersedes C-nnnn` (no colon) in body. Negative: the same selftest would fail if the field lands in cell 5 or if replacement leaves the old value. `claims_check.py --strict --count-check` and `gate.py` are regression controls on the ledger and standing gates.
4. **Scope.** Covered: `tools/board.py` `op_claim_set` and its selftest; live ledger row `C-6750`. Not covered: other claim rows with `Supersedes` in evidence (none found by the body/evidence scan used during investigation; the fix changes insertion behavior for missing keys, not existing evidence placements except replacement-in-place).
5. **Falsifier.** The claim is false if `claim-set` on a row missing `Supersedes` writes to cell 5, or if rerunning `claim-set` on C-6750 moves/duplicates `Supersedes` into evidence, or if `gate.py` is not 5 pass / 0 fail / 0 skip with `board_check` PASS and `fn_audit` not SKIP.

## Observations

Before fix (C-6750, current ledger): `BEFORE|cells 7 |sup_body True |sup_evid False`; body tail `rsedes C-6460, whose scope credited the \`ce_strfind\` run with decoded coverage. `; evidence tail `d.py archive/head256.img "VIN1:" --encoding utf-16le\` (SystemCC.dll 0x02a73a30) `.

`python3 tools/board.py --selftest` after fix: `board selftest: OK (89 checks)`.

`python3 tools/board.py claim-set C-6750 Supersedes C-6460`: `board: C-6750 Supersedes: C-6460`.

After command: `AFTER|cells 7 |sup_body True |sup_evid False`; body tail unchanged; evidence tail unchanged.

`python3 tools/claims_check.py --strict --count-check`: exit 0, `claims_check: OK — 723 rows, 0 errors, 0 warnings`.

`python3 tools/gate.py`: `PASS selftest`, `PASS claims_check` (`723 rows, 0 errors, 0 warnings`), `PASS todo_check` (`ok: 198 tasks`), `PASS board_check` (`17b22eaf1ef2 vs base 9ee75013d518: 0 task(s) and 0 claim row(s) lost, 0 exempt, 0 problem(s)`), `PASS fn_audit` (`checked=19 passed=19 failed=0 SKIP=0`); summary `gate: 5 pass / 0 fail / 0 skip`.

## Interpretation

- **FACT:** `op_claim_set` now inserts a missing key into body cell 2 and replaces existing keys in body or evidence in place; `Supersedes` matches optional colon. The selftest pins cell-2 insertion, no-evidence write, replacement, and legacy no-colon rewrite.
- **FACT:** Running `board.py claim-set C-6750 Supersedes C-6460` on the live ledger leaves `Supersedes: C-6460` in cell 2 and no `Supersedes` in cell 5; evidence unchanged.
- **OBSERVED:** `gate.py` reports 5 pass / 0 fail / 0 skip with `board_check` PASS and `fn_audit` not SKIP.
- **HYPOTHESIS:** none.
- **UNKNOWN:** none.

## Conclusion

H129 is fixed: `claim-set` no longer writes missing keys to evidence cell 5; it writes them to body cell 2, matching ledger convention. The selftest covers the regression. C-6750 was normalized by the required `board.py claim-set` command with no evidence-cell change.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/board.py --selftest   # expected: board selftest: OK (89 checks)
python3 tools/gate.py               # expected: 5 pass / 0 fail / 0 skip
```

## Follow-ups

- [ ] none
