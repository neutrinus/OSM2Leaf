# EXP-2026-11-23-H41: L1/L2 progress matrix and regression baseline

- **Status:** done · **Date:** 2026-11-23 · **Claims:** C-3280–C-3289 · Supersedes/superseded by: none
- **Sample:** `none (tool-only task)` — no vendor bytes; the H40 no-vendor registry and the committed baseline JSON are the only inputs, so no SHA-256 applies.
- **Tools:** `python3 -VV` (printed in Observations); `tools/l1l2_fixtures.py`, `tools/l1l2_matrix.py`, `tools/board.py`

### Sample-hash provenance (M9.78)

The full hashes in the Sample bullet were printed by
`sha256sum <path>` on this host on 2026-11-24; the complete command and its
output are quoted in `EXP-2026-11-24-M9.78-exp-template-defects.md` (this task's own
record). No hash in this record was typed from a prefix.


## Question

Can H40's L1/L2 checks become a per-file/per-feature matrix with honest status separation and a no-vendor regression baseline?

## Hypothesis

A reporter keyed by stable IDs reproduces statuses without promotion, and its baseline fails loudly on a regression. **Falsifier:** a non-PASS counted as PASS, a baseline green after a PASS row becomes FAIL or disappears, or a mapping with no claim/tool reference.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (no `.img`, `.DAT`, `.cmp`, `.ind`); SHA-256 n/a |
| Tool / version | `python3 -VV` at run time |
| Repo tool | `tools/l1l2_fixtures.py --json`, `tools/l1l2_matrix.py` |

## Method

1. **Sample and hash.** The 10 H40 registry checks plus the committed `tools/fixtures/l1l2-matrix-baseline.json`; no firmware/L3/L4.
2. **Commands.** (from the worktree; every number cited below is printed here):
```bash
cd /home/marek/projekty/OSM2Leaf.task-h41-l1l2-progress-matrix
D=~/projekty/leafre-work/scratch/h41-nav; mkdir -p "$D"
python3 tools/l1l2_fixtures.py --json "$D/l1l2.json" --md "$D/l1l2.md" --no-stdout-md
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'projekty/leafre-work/scratch/h41-nav'
r = json.loads((p/'l1l2.json').read_text()); s = r['summary']
print('total', s['total'], 'counts', s['counts'], 'runnable', s['runnable_pass'], s['runnable_fail'], s['runnable_skip'])
for c in r['checks']: print(c['id'], c['status'])
PY
python3 tools/l1l2_matrix.py --selftest
python3 tools/l1l2_matrix.py --input "$D/l1l2.json" --json "$D/matrix.json" --md "$D/matrix.md"
python3 tools/l1l2_matrix.py --input "$D/matrix.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json; echo "base_rc=$?"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'projekty/leafre-work/scratch/h41-nav'
r = json.loads((p/'matrix.json').read_text()); rows = r.get('rows', r.get('checks', []))
rows[next(i for i, x in enumerate(rows) if x['status'] == 'PASS')]['status'] = 'FAIL'
(p/'mutant.json').write_text(json.dumps(r)); print('mutant: one PASS -> FAIL')
PY
python3 tools/l1l2_matrix.py --input "$D/mutant.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json; echo "mutant_rc=$?"
grep -n l1l2-matrix .github/workflows/l1l2-fixtures.yml
```
3. **Controls.** Positive: the fixture run prints `total 10`, `PASS 8 / FAIL 0 / SKIP 1 / NOT COVERED 1`, runnable `8/0/1`; rows map by check ID to a claim/tool reference or `NOT_COVERED` (`l2.tile.harness-selftest` → C-3274), and the unmutated baseline gives `base_rc=0`. Negative: `mutant_rc` must be non-zero; a baseline key deleted from the report must also fail (selftest); synthetic SKIP/`NOT_COVERED`/`NOT_RUNNABLE` rows never raise the PASS count.
4. **Scope.** Only the 10 registry checks and four features (`roads,names,POIs,geometry`) with explicit evidence; other file classes are `NOT_COVERED` with a reason. No golden EU2011, no 194 REFER001 pairs, no firmware acceptance claim (rule 13). H43 consumes this baseline and key (`level,file,feature`); it must not fork a second schema.
5. **Falsifier.** A non-PASS token promoted to PASS; green baseline after PASS→FAIL or a lost row; a guessed mapping; `NOT COVERED` emitted where the schema requires `NOT_COVERED`.

## Observations

Raw output of the commands in Method step 2 (and the extra commands named
below). `python3 -VV`: `Python 3.15.0 (3.15.0-1.fc45.x86_64, Oct 9 2026,
00:00:00) [GCC 16.2.1 20260819 (Red Hat 16.2.1-2)]`.

1. Fixture run: `l1l2_fixtures: runnable 8P/0F/1S, not_covered=1, verdict=OK`,
   `fixtures_rc=0`; then `total 10 counts {'PASS': 8, 'FAIL': 0, 'SKIP': 1,
   'NOT COVERED': 1} runnable 8 0 1`. The ten statuses printed: eight PASS,
   `l2.cmpind.recompress-roundtrip SKIP`, `l2.tile.harness-selftest
   NOT COVERED`.
2. `python3 tools/l1l2_matrix.py --selftest` → `l1l2_matrix self-test:
   25/25 checks OK`, `selftest_rc=0`.
3. Matrix: `--input … --json … --md …` rc=0; report `Rows: 12; runnable 9 PASS
   / 0 FAIL / 1 SKIP (runnable total 10)`. Rows: L1 `structural` PASS;
   names (DRSTR selftest + build-roundtrip) PASS; four `container` rows
   (three PASS, one SKIP); tile harness NOT_COVERED; roads PASS; geometry
   PASS; POIs PASS; ADDRE/section-4 names NOT_COVERED. All status cells use
   underscore tokens, no `NOT COVERED` spelling survives.
4. Baseline file written by `--write-baseline`: `baseline rows 12`; SHA-256
   `22a98f28b5525e7d2bf5489febd59843cc530639e9ce482fb1e8766ec81229ac`.
5. `--check-baseline`: `base_rc=0` with `baseline matches (no regression,
   improvement or new key)`. PASS->FAIL: `REGRESSION: L1|ZE0 generated
   fixture tree|structural: PASS -> FAIL`, `mutant_rc=1`. Deleted POIs key:
   `REGRESSION: MISSING L2|REFER001/POINT0nn|POIs (was PASS)`,
   `missing_rc=1`. Selftest additionally asserts PASS->SKIP regression,
   FAIL->PASS improvement, NEW key informational.
6. Workflow: `grep -n l1l2-matrix .github/workflows/l1l2-fixtures.yml`
   prints lines 76, 80–82, 86, 98, 110, 111; `python3 -c "import yaml;
   yaml.safe_load(...)"` → `YAML OK`. README `grep -n` prints line 13
   (`Regression policy (H41/H43)`) and line 20 (`H43 consumes this same`).
7. Branch hygiene: after `git fetch origin && git rebase origin/main`,
   `python3 tools/board.py lost --base origin/main` printed `TODO.md: OK
   tasks=0 claims=0` and `docs/research/claims.md: OK tasks=0 claims=0`
   (`lost_rc=0`). `grep -c "C-328" docs/research/claims.md` printed `0`
   before `board.py add-claims`, which printed `added 10 claim row(s):
   +14 lines`. `tools/claims_check.py` → `claims_check: OK` (rc=0);
   `tools/todo_check.py` → `todo_check: OK` (rc=0).
8. Full `python3 tools/selftest.py` is host-dependent, not an H41 result:
   on this driver host it printed `passed=245 failed=1 skipped=21
   total=267 time=143.00s` (`selftest_all_rc=1`), with the builtin
   `fn_audit_l3_image` failing on `CORPUS STALE: DOCS BASE: 1 new / 0 gone /
   0 moved` and `DOCS BASE new TODO.md:0x0041f3dc fn`; `tool:l1l2_matrix
   PASS 0.04s`. On the navigator host it printed `passed=243 failed=3
   skipped=21 total=267`: two extra tool failures there were `/tmp`
   quota (`OSError Errno 122` in `identity_fields`, gcc write error in
   `sdlock_pico_check`), not H41. `python3 tools/gate.py` → `gate: 3 pass,
   2 fail, 0 skip` (`gate_rc=1`) with `CORPUS STALE: DOCS BASE: 1 new /
   0 gone / 0 moved` and `CORPUS STALE: L3 OVERLAY: 8 new / 0 gone /
   0 moved`; the new overlay lines include
   `EXP-2026-11-23-H41-l1l2-progress-matrix.md:0x0041f3dc fn` and three
   `EXP-2026-11-22-M6.19-unit-flash-map.md` VAs. Materialising HEAD twice
   with `git archive HEAD` into scratch (image symlinked) and deleting
   only this EXP gave `L3 OVERLAY: 8 new` with it and `7 new` without it:
   **this EXP itself adds one L3 OVERLAY citation.** The separate DOCS
   BASE `1 new` (`TODO.md:0x0041f3dc fn`) is genuinely pre-existing:
   `git show origin/main:TODO.md` contains that `fn 0x0041f3dc`, and the
   corpus snapshot is dated 2026-11-16.

## Interpretation

- **FACT:** The 10-check H40 registry becomes 12 keyed matrix rows with
  explicit claim/tool evidence; PASS/FAIL/SKIP/NOT_COVERED/NOT_RUNNABLE stay
  distinct, and a baseline status drop or a vanished key exits non-zero.
- **OBSERVED:** The single honest fixture gap is `l2.tile.harness-selftest`
  (C-3274); ADDRE/section-4 names is a second, data-driven `NOT_COVERED`
  gap (C-3274/C-2760). No feature was attributed without a claim/tool.
- **HYPOTHESIS:** H43 can consume this baseline and key directly; no second
  schema is needed. Not verifiable until H43 lands.
- **UNKNOWN:** Whether the pre-existing `fn_audit` corpus drift is fixed by
  an unrelated in-flight task; H41 does not touch that corpus.

**Conclusion.** `tools/l1l2_matrix.py`, its 12-row committed baseline, the
workflow step/artifact and the README regression policy implement H41's Done
when. The gate remains red on citation drift: the DOCS BASE row comes from
merged tasks, while this EXP itself contributes one of the eight L3 OVERLAY
rows (Observation 8). H41's own selftest passes 25/25 and both board
checkers pass.

## Corrections after navigator review

1. **Positive-control numbers:** replaced "6 PASS/1 SKIP" in the plan with
   the measured `total 10`, `PASS 8 / FAIL 0 / SKIP 1 / NOT COVERED 1`,
   runnable `8/0/1`; the sole gap is `l2.tile.harness-selftest` -> C-3274
   (Observations 1; C-3281).
2. **Bidirectional baseline:** `check_baseline()` ranks statuses and fails on
   a removed key; selftest covers PASS->FAIL, PASS->SKIP and MISSING, plus
   FAIL->PASS improvement (Observations 5; C-3283).
3. **Status tokens:** `normalize_status()` maps `NOT COVERED` to
   `NOT_COVERED`, emits a distinct `NOT_RUNNABLE`, and the selftest asserts
   underscore tokens and separate counts while only runnable FAIL fails the
   exit (C-3282).
4. **Mapping discipline:** `MAPPING` keys strictly the ten existing check IDs
   with claim/reader-coverage evidence; `l2.cmpind.*` stays `container` and
   ADDRE/section-4 names is an explicit `NOT_COVERED` row, never inferred;
   no line numbers or offsets are used as keys (C-3284).
5. **Branch hygiene:** rebased before any build; `lost --base origin/main`
   re-ran at 0/0; `add-claims` received explicit rows C-3280–C-3289 after
   confirming zero pre-existing hits (Observations 7; C-3288).
6. **H43 fork risk:** the baseline document's `note`, the workflow README
   and C-3286 state that H43 consumes H41's file and `level,file,feature`
   key with no second schema or `--check-baseline`.

## Reproduction

```bash
cd /home/marek/projekty/OSM2Leaf.task-h41-l1l2-progress-matrix
python3 tools/l1l2_matrix.py --selftest                       # 25/25 OK
D=~/projekty/leafre-work/scratch/h41-rec; mkdir -p "$D"
python3 tools/l1l2_fixtures.py --json "$D/l1l2.json" --md "$D/l1l2.md" --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/l1l2.json" --json "$D/matrix.json" --md "$D/matrix.md" --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/matrix.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md   # rc=0, baseline matches
# Negative 1: report PASS -> FAIL (both mutants below were re-run after the rebase)
python3 - "$D/matrix.json" "$D/mutant.json" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
r = json.load(open(src, encoding='utf-8'))
i = next(i for i, x in enumerate(r['rows']) if x['status'] == 'PASS')
print(f"mutated row {i}: {r['rows'][i]['level']}|{r['rows'][i]['file']}|{r['rows'][i]['feature']}: PASS -> FAIL")
r['rows'][i]['status'] = 'FAIL'
open(dst, 'w', encoding='utf-8').write(json.dumps(r))
PY
python3 tools/l1l2_matrix.py --input "$D/mutant.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
# printed: REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL ; rc=1
# Negative 2: delete a baseline key from the report
python3 - "$D/matrix.json" "$D/missing.json" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
r = json.load(open(src, encoding='utf-8'))
before = len(r['rows'])
r['rows'] = [x for x in r['rows']
             if not (x['level'] == 'L2' and x['file'] == 'REFER001/POINT0nn'
                     and x['feature'] == 'POIs')]
open(dst, 'w', encoding='utf-8').write(json.dumps(r))
print(f"deleted key: L2|REFER001/POINT0nn|POIs (rows {before} -> {len(r['rows'])})")
PY
python3 tools/l1l2_matrix.py --input "$D/missing.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
# printed: REGRESSION: MISSING L2|REFER001/POINT0nn|POIs (was PASS) ; rc=1
```

## Follow-ups

- [ ] H43 consumes `tools/fixtures/l1l2-matrix-baseline.json` and the
      `level,file,feature` key; do not add a second baseline schema.
- [ ] An unrelated task should refresh the `fn_audit` L3 corpus for the
      merged `0x0041f3dc` / M6.19 citations so `gate.py` is green again.
- [ ] Delete the scratch directory `~/projekty/leafre-work/scratch/h41-nav/`
      after this record is committed.

## Navigator final review (round 4)

**CHANGES** — all mandatory mutants pass: baseline stored-value edit → `REGRESSION … PASS -> SKIP`, rc=1; extra baseline key → `MISSING …`, rc=1; report PASS→FAIL → rc=1; deleting the real POIs row → `MISSING … (was PASS)`, rc=1; 12/12 keys unique on both sides; NOT-status sources map to NOT_COVERED/SKIP/NOT_RUNNABLE/FAIL with `counted_PASS 0`. Counts re-quoted: fixture 10/8/0/1/1, matrix 12/9/0/1/2, selftest 25/25, baseline SHA-256 matches.

1. Observation 8 and C-3289 cite a moved number and wrong cause. Re-run `python3 tools/gate.py` → `L3 OVERLAY: 8 new / 0 gone / 0 moved`, not `4 new`. Materialising HEAD twice and removing only this EXP (`git archive HEAD` → scratch) gives `8 new` with it, `7 new` without it: **this EXP itself adds one L3 OVERLAY citation**. Correct the count and state the self-inflicted line; keep the separate, pre-existing DOCS BASE drift (`1 new`) as not caused by H41.
2. Full `selftest.py` here prints `passed=243 failed=3 skipped=21 total=267`: two extra tool failures are `/tmp` disk-quota (`OSError Errno 122` in `identity_fields`, gcc write error in `sdlock_pico_check`), not H41. Do not call `fn_audit_l3_image` "the sole FAIL" without naming the host/quota condition.
3. Reproduction block still elides the missing-key mutation behind a comment; paste the exact delete-and-recheck commands (or point to the shipped selftest check by name) so both negatives are re-runnable.

## conclusion

See the result in the Status line and the conclusion reached in the Observations/Interpretation above; this repair adds no new claim.

## overtaken by a later commit

none
