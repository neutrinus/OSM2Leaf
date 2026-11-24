# EXP-2026-11-24-H57: Fixture regression baseline and monotone PASS->FAIL gate

- **Status:** done · **Date:** 2026-11-24 · **Claims:** C-3730–C-3739 · Supersedes: none
- **Sample:** none (tool-only task) — committed JSON fixture baseline and the H40/H41 generated fixture; no `.img`/`.DAT`/`.cmp`/`.ind` bytes
- **Tools:** `python3 -VV` printed `Python 3.15.0 (3.15.0-1.fc45.x86_64, Oct  9 2026, 00:00:00) [GCC 16.2.1 (Red Hat 16.2.1-2)]`; repo tools `tools/l1l2_matrix.py`, `tools/l1l2_fixtures.py`, `tools/progress_snapshot.py`, `tools/selftest.py`, `tools/todo_check.py`, `tools/claims_check.py`
- **Claims:** C-3730–C-3739
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the H41/H56 generated-fixture baseline enforce H57's PASS->FAIL rule end to end — including `SKIP -> FAIL` — with a committed no-vendor file and documented refresh policy?

## Hypothesis

The committed baseline file and `--check-baseline` already landed by H41/H43 enforce PASS->FAIL, but the rank model `PASS=4, FAIL=3, SKIP=2` promotes `SKIP -> FAIL` to an IMPROVEMENT. Replacing it with monotone tiers (`PASS > honest non-PASS > FAIL`) makes every true degradation fail while honest rises stay informational. **Falsifier:** after the change, a `SKIP -> FAIL` mutation still prints IMPROVEMENT with rc=0, or the committed baseline no longer matches itself (rc!=0), or PASS->FAIL/P->SKIP stop failing.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only; committed JSON) |
| SHA-256 | `22a98f28b5525e7d2bf5489febd59843cc530639e9ce482fb1e8766ec81229ac` — `tools/fixtures/l1l2-matrix-baseline.json` (quoted from `sha256sum tools/fixtures/l1l2-matrix-baseline.json`) |
| Offset(s) / VA(s) | n/a |
| Tool / version | Python 3.15.0 / stock zlib on this host (no byte-identical recompression claim) |
| Repo tool | `tools/l1l2_matrix.py` (the tool that produced the numbers) |

## Method

### 1. Sample and hash

`tools/fixtures/l1l2-matrix-baseline.json`, SHA-256 `22a98f28b5525e7d2bf5489febd59843cc530639e9ce482fb1e8766ec81229ac` (printed by `sha256sum`). No vendor bytes.

### 2. Commands

```bash
cd /home/marek/projekty/OSM2Leaf.task-h57-fixture-baseline
D=~/projekty/leafre-work/scratch/scratch/h57; mkdir -p "$D"
sha256sum tools/fixtures/l1l2-matrix-baseline.json
python3 -c "import json,collections; d=json.load(open('tools/fixtures/l1l2-matrix-baseline.json')); c=collections.Counter(r['status'] for r in d['rows']); print('rows',len(d['rows']),'counts',dict(c))"
python3 -c "import json; d=json.load(open('tools/fixtures/l1l2-matrix-baseline.json')); print('schema',d['schema'],'key',d['key'],'task',d['task'])"
python3 tools/l1l2_matrix.py --selftest
python3 tools/l1l2_matrix.py --input tools/fixtures/l1l2-matrix-baseline.json --json "$D/current.json" --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/current.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'projekty/leafre-work/scratch/scratch/h57'
r = json.loads((p/'current.json').read_text())
for label, old, new in [('pass2fail','PASS','FAIL'),('pass2skip','PASS','SKIP'),('skip2fail','SKIP','FAIL')]:
    m = json.loads(json.dumps(r))
    row = next(x for x in m['rows'] if x['status']==old)
    row['status'] = new
    (p/f'{label}.json').write_text(json.dumps(m))
    print(label, row['level'], row['file'], row['feature'])
PY
python3 tools/l1l2_matrix.py --input "$D/pass2fail.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/pass2skip.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/skip2fail.json" --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
python3 tools/selftest.py --only l1l2_matrix
mkdir -p ~/projekty/leafre-work/scratch/h57/tmp
TMPDIR=~/projekty/leafre-work/scratch/h57/tmp python3 tools/selftest.py --json > ~/projekty/leafre-work/scratch/h57/selftest-full.json
python3 -c "import json; d=json.load(open('$HOME/projekty/leafre-work/scratch/h57/selftest-full.json')); print('ok',d['ok'],'counts',d['counts'])"
python3 tools/todo_check.py
python3 tools/claims_check.py --strict --count-check
```

### 3. Controls

- **Positive:** the committed baseline compared with its own report prints no messages and rc=0; `--selftest` prints 31/31 checks OK; PASS->FAIL and PASS->SKIP each print `REGRESSION` rc=1; `SKIP -> FAIL` prints `REGRESSION` rc=1 (the previously broken case).
- **Negative (before the fix):** navigator reproduced `IMPROVEMENT: L2|REFER001/*.cmp/.ind (recompress)|container: SKIP -> FAIL` with rc=0 from the rank model (see `H57-method.txt`); that is the defect under repair, not a result of the current tool.
- **Improvement control:** FAIL->PASS, FAIL->SKIP and SKIP->PASS are printed `IMPROVEMENT` with no REGRESSION (selftest asserts each).
- **Set controls:** a vanished PASS key fails (`REGRESSION: MISSING ... was PASS`), a vanished non-PASS key is `DROPPED` (printed, rc unaffected), a duplicate key is `DUPLICATE`, a new key is `NEW` — all asserted in `--selftest`.

### 4. Scope

The H40/H41 generated fixture: the committed baseline has 12 rows (`PASS 9, SKIP 1, NOT_COVERED 2`, printed by the `Counter` command) keyed by `level,file,feature`; L1 structural plus L2 names/container/roads/geometry/POIs. Excluded: no vendor data, no golden EU2011 bytes, no full 194 REFER001 pairs, no firmware/L3/L4/L5 acceptance claim (rule 13). H104's L1 `cardcheck` baseline is a separate task and is untouched; H41's `--check-baseline` and baseline schema are reused, not forked.

### 5. Falsifier

If after the fix `SKIP -> FAIL` still prints IMPROVEMENT rc=0, the fix is incomplete; if the committed baseline no longer matches itself, or PASS->FAIL/P->SKIP stop failing, the fix over-corrected. Stated before the result.

## Observations

Raw output of the Method step 2 commands (at HEAD `7d2d3e11`, branch `task/h57-fixture-baseline`):

1. `sha256sum tools/fixtures/l1l2-matrix-baseline.json` → `22a98f28b5525e7d2bf5489febd59843cc530639e9ce482fb1e8766ec81229ac  tools/fixtures/l1l2-matrix-baseline.json`.
2. `Counter` command → `rows 12 counts {'PASS': 9, 'SKIP': 1, 'NOT_COVERED': 2}`. Schema command → `schema osm2leaf.l1l2-matrix-baseline/v1 key ['level', 'file', 'feature'] task H41`.
3. `python3 tools/l1l2_matrix.py --selftest` → `l1l2_matrix self-test: 31/31 checks OK`.
4. Build-and-check: `--input tools/fixtures/l1l2-matrix-baseline.json --json …/current.json` rc=0; `--input …/current.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json` rc=0, no output.
5. Mutants (mutation script prints the chosen row): `pass2fail L1 ZE0 generated fixture tree structural`, `pass2skip L1 ZE0 generated fixture tree structural`, `skip2fail L2 REFER001/*.cmp/.ind (recompress) container`. Their gate results:
   - `REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL`, rc=1.
   - `REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> SKIP`, rc=1.
   - `REGRESSION: L2|REFER001/*.cmp/.ind (recompress)|container: SKIP -> FAIL`, rc=1.
6. `python3 tools/selftest.py --only l1l2_matrix` → `tool:l1l2_matrix  PASS`, `passed=1 failed=0 skipped=0 total=1`, `selftest: OK` (the timing suffix is host-dependent and is not quoted).
7. Full `python3 tools/selftest.py --json` with `TMPDIR` on the home tree → `ok True counts {'pass': 282, 'fail': 0, 'skip': 21, 'total': 303}` (elapsed 149.437s); `tool:l1l2_matrix` status PASS with output `l1l2_matrix self-test: 31/31 checks OK`; no FAIL entries. Earlier runs with the default `/tmp` tmpfs printed `passed=278 failed=4 skipped=21 total=303 time=810.41s; selftest: FAILED` (an `l3_harness.engine` 60s timeout) and `271/11/21/303` when the tmpfs filled — host churn, not H57 failures. The completed JSON is cited in Interpretation.
8. `python3 tools/todo_check.py` → `todo_check: OK` (rc=0; two pre-existing WARNs about M9.63/M9.72 dependencies). `python3 tools/claims_check.py --strict --count-check` → `claims_check: OK` (rc=0).
9. `git ls-files | grep -i baseline` names three paths (`tools/fixtures/l1l2-matrix-baseline.json`, `tools/fixtures/todo_strict_baseline.json` and an EXP). `grep -n baseline .github/workflows/*.yml` names the baseline step in `l1l2-fixtures.yml` and the policy prose in `README.md`; the task's Precheck was written before H41/H43 landed and is stale.

## Interpretation

- **FACT:** the committed baseline already exists (H41/H43) with schema `osm2leaf.l1l2-matrix-baseline/v1`, 12 rows, key `level,file,feature`; H57 does not add a second schema or a second `--check-baseline`.
- **FACT:** the old rank order promoted `SKIP -> FAIL` to IMPROVEMENT with rc=0, so a genuine degradation stayed green; the new monotone tier order makes it a REGRESSION rc=1 (observation 5).
- **FACT:** all honest non-PASS tokens share one tier; a move among them (e.g. SKIP->NOT_COVERED) is intentionally neither a regression nor an improvement, as documented in `tools/l1l2_matrix.py` and asserted in `--selftest`.
- **OBSERVED:** a lost PASS key fails while a lost non-PASS key is DROPPED; duplicates are reported. This implements H57's DROPPED/NEW hints without weakening the PASS gate.
- **HYPOTHESIS:** `progress_snapshot.py`, which composes `l1l2_matrix.py --check-baseline`, inherits the corrected verdict with no change (it reads `REGRESSION:` messages from the matrix report) — plausible from the code path but not re-run end to end in this EXP.
- **FACT:** full `selftest.py --json` with a home-tree `TMPDIR` is green on this branch (`ok True`, 282 pass / 0 fail / 21 skip / 303 total), so H57's Done-when `selftest.py passes` is met. The red runs seen with default `/tmp` are tmpfs-host churn (60s tool timeouts / ENOSPC), not caused by H57.
- **UNKNOWN:** nothing about firmware, L3/L4/L5 acceptance or vendor bytes is established by this task (rule 13).

## Conclusion

H57 closes as the L2 baseline-policy task: the committed no-vendor baseline and `--check-baseline` gate already landed with H41/H43 (recorded as C-3730/C-3731), and this pass fixes the one broken case — `SKIP -> FAIL` is now a REGRESSION — plus the missing `docs/research/test-system.md` §6 policy paragraph (C-3738). The baseline is refreshed only with an EXP/PR rationale, never to make a failure pass. H104 remains open as the separate L1 `cardcheck` baseline. Recorded in C-3730–C-3739.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/l1l2_matrix.py --selftest
python3 tools/l1l2_matrix.py --input tools/fixtures/l1l2-matrix-baseline.json --json /tmp/opencode/h57-current.json --no-stdout-md
python3 tools/l1l2_matrix.py --input /tmp/opencode/h57-current.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json --no-stdout-md
```

## Follow-ups

- [ ] H104 owns the L1 `cardcheck` committed baseline; this EXP does not touch it.
- [ ] Run the full `tools/gate.py` on a host with a fresh fn_audit corpus before merge (reported in the PR body, not this EXP).

## Corrections after navigator review

(none yet — filled after review)
