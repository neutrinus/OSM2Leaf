# EXP-2026-11-23-H56: Per-level generated-card progress snapshot

- **Status:** done · **Date:** 2026-11-23 · **Claims:** C-3720–C-3729 · Supersedes/superseded by: none
- **Sample:** none (tool-only task) — generated no-vendor fixture, synthetic JSON; no SHA-256 applies
- **Tools:** `python3 -VV` printed in Observations; `tools/progress_snapshot.py` (new, SHA-256 of first working copy `97f3fbcbd8d7ae9bfe564863767ce194dbe1251f18af4ec239940796a402f3c6`), `tools/progress_report.py` (schema v3), `tools/l3check.py`, `tools/l1l2_fixtures.py`, `tools/l1l2_matrix.py`
- **Supersedes:** none

## Question

Can one command, from a generated no-vendor fixture, print a per-level progress table (L1/L2/L3 + L4-emulator/L5-bench readiness) that separates PASS from SKIP/NOT_COVERED/NOT_RUNNABLE/BLOCKED/NOT RUN and fails on a PASS→FAIL regression?

## Hypothesis

A thin driver composing the existing H41/H55/H27 tools prints the required table without promoting non-PASS states; an H41 baseline regression or a runnable FAIL makes it exit non-zero. **Falsifier:** any non-PASS token counted as PASS, a synthetic L3 PASS reported as firmware proof, an L4/L5 row auto-PASSed without evidence, or exit 0 after a PASS→FAIL fixture mutation.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (no `.img`, `.DAT`, `.cmp`, `.ind`); H40 generated fixture + synthetic JSON |
| SHA-256 | n/a (no vendor bytes) |
| Tool / version | `python3 -VV` printed in Observations |
| Repo tool | `tools/progress_snapshot.py` (produced all H56 numbers) |
| Baseline | `tools/fixtures/l1l2-matrix-baseline.json` SHA-256 `22a98f28b5525e7d2bf5489febd59843cc530639e9ce482fb1e8766ec81229ac` |

## Method

1. **Sample/corpus.** The generated H40 registry (10 checks), the committed 12-row H41 baseline, the H55 `--build-corpus` L3 report (13 targets) and three navigator-written synthetic JSON fixtures. No firmware image, QEMU or network; nothing from `archive/`.
2. **Commands** (from the worktree; every number quoted below is printed by one of these):
```bash
cd /home/marek/projekty/OSM2Leaf.task-h56-progress-snapshot
D=~/projekty/leafre-work/scratch/h56; mkdir -p "$D"

# baseline selftest
python3 tools/progress_report.py --selftest; echo "report_selftest_rc=$?"
python3 tools/progress_snapshot.py --selftest; echo "snapshot_selftest_rc=$?"

# real one-command snapshot (runs l1l2_fixtures -> l1l2_matrix + baseline ->
# l3check --build-corpus --json -> progress_report.py)
python3 tools/progress_snapshot.py --out "$D/snap1" \
    --json "$D/snapshot.json" --md "$D/snapshot.md"; echo "snapshot_rc=$?"

# H55 L3 report used above (prints its own counts; ~1 s wall time)
time python3 tools/l3check.py --build-corpus --json "$D/real-l3.json"; echo "l3_rc=$?"
python3 - "$D/real-l3.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
from collections import Counter
print('l3 schema', d.get('schema'), 'result', d.get('result'), 'counts', d.get('counts'))
print('l3 targets', len(d.get('targets', [])), 'statuses', dict(Counter(t.get('status') for t in d.get('targets', []))))
PY

# H41 matrix + baseline numbers behind L1/L2
python3 tools/l1l2_fixtures.py --json "$D/l1l2.json" --no-stdout-md
python3 tools/l1l2_matrix.py --input "$D/l1l2.json" --json "$D/matrix.json" \
    --check-baseline tools/fixtures/l1l2-matrix-baseline.json; echo "matrix_rc=$?"
python3 - "$D/snapshot.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print('exit_code', d['exit_code'], 'problems', d['problems'])
print('baseline rc', d['baseline']['rc'], 'msgs', d['baseline']['messages'], 'regressions', d['baseline']['regressions'])
PY

# mandatory negative mutation: one PASS -> FAIL in the H40 fixture
cp "$D/snap1/l1l2.json" "$D/l1l2-mutant.json"
python3 - "$D/l1l2-mutant.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); n = 0
for c in d.get('checks', []):
    if c.get('status') == 'PASS':
        c['status'] = 'FAIL'; n += 1; break
open(p, 'w').write(json.dumps(d)); print('mutated PASS->FAIL checks:', n)
PY
python3 tools/l1l2_matrix.py --input "$D/l1l2-mutant.json" \
    --check-baseline tools/fixtures/l1l2-matrix-baseline.json; echo "matrix_mutant_rc=$?"
python3 tools/progress_snapshot.py --l1l2-input "$D/l1l2-mutant.json" \
    --l3-input "$D/real-l3.json" --out "$D/snap-mutant2"; echo "mutant_snapshot_rc=$?"

# navigator synthetic L3 controls against the real L1/L2 fixture
python3 tools/progress_snapshot.py --l1l2-input "$D/snap1/l1l2.json" \
    --l3-input "$D/synth-l3-1pass.json" --out "$D/snap-l3pos" | grep -E '^\| (L3|L4|L5)|firmware-proof'
python3 tools/progress_snapshot.py --l1l2-input "$D/snap1/l1l2.json" \
    --l3-input "$D/synth-l3-skipblock.json" --out "$D/snap-l3neg" | grep -E '^\| (L3|L4|L5)|firmware-proof'

# board/gate checks
git fetch origin && git rebase origin/main
python3 tools/board.py lost --base origin/main; echo "lost_rc=$?"
python3 tools/todo_check.py; echo "todo_rc=$?"
python3 tools/claims_check.py; echo "claims_rc=$?"
python3 tools/selftest.py --only progress_snapshot; echo "selftest_only_rc=$?"
python3 tools/gate.py; echo "gate_rc=$?"
```
The three navigator synthetic fixtures under `$D` (`synth-l1l2-matrix.json`,
`synth-l3-1pass.json`, `synth-l3-skipblock.json`) are reproduced verbatim in
`~/projekty/leafre-work/scratch/h56/EXP-method.md` §Method 2; they are scratch,
never committed. The L3 control fixtures are:
```bash
cat > "$D/synth-l3-1pass.json" <<'EOF'
{"schema":"osm2leaf.l3check/v1","result":"PASS",
 "counts":{"pass":1,"fail":0,"skip":0,"blocked":0},
 "targets":[{"name":"probe-zlib-cmf","reader":"synthetic","status":"PASS",
             "synthetic":true,"l3_claim":false,"claims":[]}]}
EOF
cat > "$D/synth-l3-skipblock.json" <<'EOF'
{"schema":"osm2leaf.l3check/v1","result":"NOT_YET_AVAILABLE",
 "counts":{"pass":0,"fail":0,"skip":1,"blocked":1},
 "targets":[
   {"name":"probe-skip","reader":"synthetic","status":"SKIP","synthetic":true,"l3_claim":false,"claims":[]},
   {"name":"drstr-reader","reader":"drstr","status":"BLOCKED","synthetic":false,"l3_claim":false,"claims":[]}]}
EOF
```
3. **Controls.** Positive: the real snapshot prints L1 `1 PASS`, L2 `8 PASS / 1 SKIP / 2 NOT_COVERED`, L3 `3 PASS / 10 BLOCKED` with 2 firmware-proof and 1 synthetic PASS; L4/L5 both `NOT RUN (hardware/QEMU unavailable)`; `exit_code=0`, `problems=[]`, baseline rc=0, no regressions. The 1-synthetic-PASS fixture prints `L3 | 1 | 0 | 0 | 0 | 0 | 0 | PASS` and `firmware-proof PASS=0, synthetic PASS (not firmware proof)=1`. Negative A: the SKIP+BLOCKED fixture prints `L3 | 0 | 0 | 1 | 0 | 0 | 1 | NO RUNNABLE CHECK` and 0 firmware/synthetic PASS. Negative B: the PASS→FAIL mutation makes `l1l2_matrix` and the full snapshot both exit 1, prints `REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL`, and L1 flips to `0 PASS / 1 FAIL / verdict FAIL`.
4. **Scope.** One generated H40 fixture (10 registry checks → 12 matrix rows), one H41 baseline (12 rows), one H55 build-corpus L3 report (13 targets: 3 PASS, 10 BLOCKED), two synthetic L3 fixtures (1 PASS; 1 SKIP + 1 BLOCKED), plus `--selftest` 27 checks with a synthetic PASS→FAIL mutation. No L4/QEMU execution, no bench/car, no vendor image, no network, no firmware acceptance claim (rule 13). L4/L5 rows are readiness flags only.
5. **Falsifier check.** A SKIP/BLOCKED/NOT_RUNNABLE/NOT_COVERED/NOT RUN row promoted to PASS; a synthetic L3 PASS promoted to firmware proof; an L4/L5 auto-PASS without evidence; exit 0 after the mutation; or any step reading vendor bytes / launching QEMU / hitting the network.

## Observations

Raw output of the commands in Method step 2.

1. `python3 -VV`: `Python 3.15.0 (3.15.0-1.fc45.x86_64, Oct 9 2026, 00:00:00) [GCC 16.2.1 20260819 (Red Hat 16.2.1-2)]`.
2. `progress_report.py --selftest`: `progress_report selftest: OK`, `report_selftest_rc=0`. `progress_snapshot.py --selftest`: `progress_snapshot self-test: 27/27 checks OK`, `snapshot_selftest_rc=0`.
3. Real snapshot (printed table, identical to `$D/snapshot.md`):
```
| level | runnable PASS | FAIL | SKIP | NOT_COVERED | NOT_RUNNABLE | BLOCKED | verdict |
| L1 | 1 | 0 | 0 | 0 | 0 | 0 | PASS |
| L2 | 8 | 0 | 1 | 2 | 0 | 0 | PASS WITH GAPS |
| L3 | 3 | 0 | 0 | 0 | 0 | 10 | PASS WITH GAPS |
| L4-emulator | 0 | 0 | 0 | 0 | 0 | 0 | NOT RUN (hardware/QEMU unavailable) |
| L5-bench | 0 | 0 | 0 | 0 | 0 | 0 | NOT RUN (hardware/QEMU unavailable) |
L3 firmware-proof PASS=2, synthetic PASS (not firmware proof)=1.
```
`snapshot_rc=0`.
4. `l3check --build-corpus --json`: `real 0m1.057s`, `l3_rc=0`, 17,812 bytes; `l3 schema osm2leaf.l3check/v1 result PASS counts {'pass': 3, 'fail': 0, 'skip': 0, 'blocked': 10, 'runnable': 3, 'total': 13}`; `l3 targets 13 statuses {'BLOCKED': 10, 'PASS': 3}`. The three PASS rows: `probe-zlib-cmf synthetic=True l3_claim=False fp=False ev=unknown corpus=synthetic`, `point_walk_us2011 synthetic=False l3_claim=True fp=True ev=firmware_proof corpus=unknown`, `poi_record_decode synthetic=False l3_claim=True fp=True ev=firmware_proof corpus=unknown`.
5. `l1l2_fixtures`: `l1l2_fixtures: runnable 8P/0F/1S, not_covered=1, verdict=OK`; `matrix_rc=0`. Snapshot JSON: `exit_code 0 problems []`; `baseline rc 0 msgs [] regressions []`.
6. Mutation: `mutated PASS->FAIL checks: 1`; `matrix_mutant_rc=1` with `REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL`. Full snapshot: `mutant_snapshot_rc=1`; L1 row `| L1 | 0 | 1 | 0 | 0 | 0 | 0 | FAIL |`, baseline line `REGRESSION: L1|ZE0 generated fixture tree|structural: PASS -> FAIL`.
7. Synthetic L3 positive: `| L3 | 1 | 0 | 0 | 0 | 0 | 0 | PASS |` and `L3 firmware-proof PASS=0, synthetic PASS (not firmware proof)=1`; L4/L5 `NOT RUN` rows. Synthetic L3 negative: `| L3 | 0 | 0 | 1 | 0 | 0 | 1 | NO RUNNABLE CHECK |` and `L3 firmware-proof PASS=0, synthetic PASS (not firmware proof)=0`.
8. Board/gate (`gate_rc=1`, all four H56-relevant gates PASS). Run 1, default `/tmp`:
```
GATE          RESULT    SECS  NOTE
------------  ------  ------  ----------------------------------------
selftest      FAIL    429.98  exit 1
claims_check  PASS     71.91
todo_check    PASS      0.56
board_check   PASS      0.53
fn_audit      PASS     22.58

--- selftest output (failures) ---
tool:identity_fields             FAIL  exit 1 (0.09s)
tool:sdlock_pico_check           FAIL  exit 1 (3.67s)
  | FAIL: build
passed=267 failed=2 skipped=21 total=290 time=387.51s
selftest: FAILED
gate: 4 pass, 1 fail, 0 skip
```
The two failures are `OSError [Errno 122] Disk quota exceeded` writing to `/tmp` (3.8 GiB tmpfs under a 3095M hard quota), **environmental, not H56** — these are the exact suites M9.79 (same batch) fixes. Run 2 and 3 with the home-tree `TMPDIR=/home/marek/projekty/leafre-work/scratch/h56/tmp` clear the quota but hit a different, timing-sensitive flake: `tool:ci_gate_repro FAIL timeout after 60s (60.07s)`, `passed=268 failed=1 skipped=21 total=290`, `gate: 4 pass, 1 fail, 0 skip` (both runs). Standalone `python3 tools/ci_gate_repro.py --selftest` prints `ci_gate_repro selftest: OK` in `real 0m56,376s`, i.e. 56 s against the gate's 60 s per-suite timeout under this batch's parallel load; it passes on an unloaded host. `fn_audit` reports `CORPUS OK` (0 new / 0 gone / 0 moved); there is no corpus drift to record. Board: `lost` tasks=0/claims=0; `todo_check.py`/`claims_check.py` OK; `selftest.py --only progress_snapshot` PASS (`27/27`).
9. No vendor bytes, QEMU process or network call was made by any H56 command; the tool composes only the listed repo tools on generated/synthetic JSON.

## Interpretation

- **FACT:** One command prints a five-row table with all required columns. On the generated fixture the counts are L1 1 PASS, L2 8 PASS / 1 SKIP / 2 NOT_COVERED, L3 3 PASS / 10 BLOCKED, L4/L5 NOT RUN; SKIP/NOT_COVERED/BLOCKED/NOT RUN are in separate columns and verdicts stay `PASS WITH GAPS`/`NOT RUN`, never bare PASS.
- **FACT:** The 1-synthetic-PASS control reports 0 firmware-proof passes; the SKIP+BLOCKED control reports no PASS. No non-PASS token was counted as PASS and no synthetic L3 PASS was promoted (rule 13).
- **FACT:** A PASS→FAIL mutation makes both the H41 baseline check and the full snapshot exit 1 and flips L1 to `FAIL`.
- **OBSERVED:** L3 `3 PASS` includes 2 non-synthetic `l3_claim` firmware-proof targets (`point_walk_us2011`, `poi_record_decode`) from the H55 harness; those are firmware fragment harness results, not L4/L5 acceptance.
- **HYPOTHESIS:** H42/H57 can consume this single table as the PR job summary without repeating the chain; not verifiable within H56.
- **UNKNOWN:** The standing gate is not fully green on this host, for two environmental reasons unrelated to H56: the default `/tmp` run fails `identity_fields`/`sdlock_pico_check` on tmpfs `EDQUOT` (the exact suites M9.79 fixes), and the home-tree-`TMPDIR` run fails the timing-sensitive `ci_gate_repro` at its 60 s gate timeout (standalone 56 s, `selftest: OK`). All four H56-relevant gates — `claims_check`, `todo_check`, `board_check`, `fn_audit` — PASS, and `fn_audit` reports `CORPUS OK` with no drift. No full-gate-green claim is made.

2. Round-2 documentation corrections (navigator final review): (a) recorded the actual full-gate result instead of claiming green — default `/tmp` run RED on `identity_fields`/`sdlock_pico_check` from tmpfs `EDQUOT` (M9.79's fix), home-`TMPDIR` runs RED on the 60 s `ci_gate_repro` timeout flake (standalone 56 s, `selftest: OK`), all four H56-relevant gates PASS with `fn_audit` `CORPUS OK` (Observations 8); (b) replaced the stale EXP UNKNOWN line about H41 corpus drift with the `/tmp`-quota finding and updated C-3729 to quote both gate runs.

## Conclusion

`tools/progress_snapshot.py` implements H56's Done when: one command prints the required table, `--selftest` (27 checks) covers status separation and the PASS→FAIL mutation, the default path needs no vendor data/QEMU/network, and the EXP records a real run. L4/L5 remain explicit NOT RUN readiness flags. Claims C-3720–C-3729 support these facts.

## Corrections after navigator review

1. **Method invariants.** Implemented all five approved invariants: L4/L5 default `NOT RUN (hardware/QEMU unavailable)`; evidenced status JSON required before any manual PASS; non-PASS separated never PASS; PASS→FAIL mutation exits 1; `--selftest` auto-discovered by `selftest.py`.
2. **L3 synthetic control.** The navigator's 1-PASS synthetic fixture is reported as `L3 PASS` in the snapshot table but with `firmware-proof PASS=0, synthetic PASS=1` printed alongside, so the row is never mistaken for firmware proof; the SKIP+BLOCKED fixture yields `NO RUNNABLE CHECK`.
3. **L1/L2 synthetic baseline.** The navigator's 6-row synthetic H41 matrix does not match the committed 12-row baseline keys; such a run reports `MISSING` baseline regressions (honest, not suppressed). The positive/negative L3 controls therefore use the real H40 L1/L2 fixture so baseline noise does not obscure the L3 status separation.
4. **Baseline coupling.** Added `--baseline` to the driver so its selftest can build a matching synthetic baseline; without it the selftest's synthetic fixture would fail the committed baseline and could not prove exit 0 on a clean run.
5. **L3 timing.** The navigator's shell timed out `l3check --build-corpus --json` at 120 s; on this host it completed in `0m1.057s` with 17,812 bytes (Observation 4). No count is quoted from a timed-out run.

## Overtaken by a later commit

No later task changes a count or status cited here at the time of writing. If H42 wires this table into CI, that task should link this EXP and update the mapping rather than redefining the schema.
