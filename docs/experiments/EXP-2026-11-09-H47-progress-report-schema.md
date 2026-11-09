# EXP-2026-11-09-H47: progress_report schema contract for H41/H43 (v3)

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** `none (tool-only task; synthetic JSON fixtures embedded in selftest and in this EXP; no vendor data)`
- **Tools:** `python3` (repo environment, stdlib only), repo tools `tools/progress_report.py`, `tools/progress_schema.py`, `tools/claims_check.py`, `tools/todo_check.py`, `tools/selftest.py`. No external dependencies.
- **Claims:** C-3360, C-3361, C-3362, C-3363, C-3364
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `progress_report.py` accept future H41 per-file/per-feature L1/L2 and H43 generated-corpus L3 JSON shapes through an explicit, testable, versioned schema contract without guessing unfinished key names, while preserving legacy H26/H27 inputs and rule-13/L1-L5 separation?

## Hypothesis

none / exploratory (contract/tooling task, H41/H43 final key names not fixed at landing time). **Falsifier:** legacy H26/H27 inputs stop parsing; a synthetic H41 matrix collapses SKIP/NOT_COVERED/NOT_RUNNABLE into PASS or loses per-file/per-feature counts; a generated-fixture H43 corpus PASS is promoted to firmware proof without an explicit non-synthetic `l3_claim`/`firmware_proof` marker; L4 emulator or L5 bench states auto-pass without recorded evidence; or `--json` output omits schema version/field contract documentation.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` |
| SHA-256 | `n/a` |
| Offset(s) / VA(s) | `n/a` |
| Tool / version | `python3 tools/progress_report.py --selftest` |
| Repo tool | `tools/progress_report.py`, `tools/progress_schema.py` |
| Task specs | `TODO.md` H47, H41, H43, H27; `docs/research/claims.md` C-2770–C-2779 |

## Method

1. **Sample and hash.** No vendor/sample bytes. All fixtures are synthetic JSON objects constructed in `progress_report.selftest()` and reproduced below; no files outside the repo/temp dirs are required.

2. **Commands.** Runnable as written from repo root/worktree:

```bash
# H47 contract selftest (covers legacy parse, H41 matrix, H43 corpus, L4/L5 manual)
python3 tools/progress_report.py --selftest

# JSON output documents schema version and field names
python3 tools/progress_report.py --help
python3 - <<'PY'
import json, tempfile
from pathlib import Path
import tools.progress_report as pr
class A: pass
a=A(); a.l1l2_json=a.l3_json=a.l1l2_matrix_json=a.l3_corpus_json=None
a.reader_coverage='docs/research/reader-coverage.md'; a.todo='TODO.md'; a.claims='docs/research/claims.md'
a.l4_status=a.l5_status=a.l4_emulator_status=None; a.run_tools=False
r=pr.build_report(a)
print(r['schema'], r['schema_version'])
print(sorted(r['schema_contract'].keys())[:8])
PY

# Repo gates
python3 tools/selftest.py
python3 tools/claims_check.py
python3 tools/todo_check.py TODO.md
```

3. **Controls.** *Positive (legacy H26/H27):* a legacy `l1l2_fixtures` object `{summary,checks,firmware_acceptance_claim:false,vendor_data_used:false}` normalizes with `kind=l1l2_legacy`, preserved verdict/summary/checks; a legacy `osm2leaf.l3check/v1` object with a synthetic PASS (`synthetic:true,l3_claim:false`) and a BLOCKED target normalizes with `kind=l3_legacy`, `firmware_proof_passes=0`, synthetic pass counted separately. *Positive (H41):* a synthetic matrix with rows covering PASS/SKIP/NOT_COVERED/NOT_RUNNABLE/FAIL and per-file/per-feature keys produces exact counts and `by_file`/`by_feature` breakdowns; an unknown row key (`tbd_key`) is preserved. *Positive (H43 explicit proof):* a generated-fixture target with `ran_on_our_generated_data:true, corpus_kind:generated_fixture, l3_claim:true, firmware_proof:true, status:PASS` is counted as firmware proof; a factory non-synthetic `l3_claim` PASS is counted as firmware proof. *Negative (rule 13):* a generated-fixture harness PASS (`l3_claim:false`, `evidence_kind:harness_only`) is not promoted to firmware proof; a synthetic PASS is never firmware proof even if fields are misleading; L4 emulator and L5 bench `PASS` without evidence are demoted to `NOT RUN`. *Negative (promotion guard):* legacy `firmware_acceptance_claim:true` is flagged.

4. **Scope.** Covered: `tools/progress_report.py` normalization/aggregation/rendering/CLI/selftest and new `tools/progress_schema.py` constants/helpers; synthetic JSON fixtures only; full-repo report generation against committed `docs/research/reader-coverage.md`, `TODO.md`, `docs/research/claims.md`. Excluded: H41/H43 final producer implementations (open); real vendor/factory/generated fixture files; CI workflow wiring (H42); any M8/QEMU run or L5 bench execution; changes to `l1l2_fixtures.py` or `l3check.py` output producers.

5. **Falsifier.** Any of: legacy H26/H27 input raises/loses stable fields; H41 `SKIP`/`NOT_COVERED`/`NOT_RUNNABLE` counted as PASS or missing from per-file/per-feature counts; H43 generated-fixture non-proof PASS reported as firmware proof; explicit-evidence requirement removed from L4/L5; `--json` missing `schema_version`/`schema_contract`; or a selftest requiring vendor data/network.

## Observations

Observed by running the commands above in the H47 worktree:

```text
$ python3 tools/progress_report.py --selftest
  ok: parses 30 reader-coverage rows, got 30
  ok: legacy H26 l1l2 detected
  ok: valid legacy l1l2 normalized
  ok: legacy l1l2 fields preserved
  ok: legacy l3check detected
  ok: synthetic PASS not counted as firmware proof
  ok: H41 matrix detected
  ok: H41 PASS count
  ok: H41 SKIP separated
  ok: H41 NOT_COVERED separated
  ok: H41 NOT_RUNNABLE separated
  ok: H41 per-file counts
  ok: H41 per-feature counts
  ok: H41 unknown keys preserved/tolerated
  ok: H43 corpus detected
  ok: H43 generated-fixture targets counted
  ok: H43 explicit firmware proof counted
  ok: generated-fixture harness PASS not promoted to firmware proof
  ok: generated-fixture harness evidence kind
  ok: explicitly marked generated-fixture firmware proof accepted
  ok: synthetic probe never firmware proof
  ok: factory non-synthetic l3_claim PASS is firmware proof
  ok: generated BLOCKED not a pass
  ok: L5/car defaults to NOT RUN, never auto-pass
  ok: L5 PASS without evidence demoted
  ok: L4/emulator defaults to NOT RUN
  ok: L4 emulator PASS without evidence demoted
  ok: L4 emulator PASS with evidence accepted
  ok: schema v3 set
  ok: schema_version present
  ok: schema_contract documents field names/versions
  ok: schema_contract documents H41 matrix input
  ok: schema_contract documents H43 corpus input
  ok: separation states generated-fixture L3 evidence
  ok: markdown shows H41 matrix breakdown
  ok: markdown shows H43 corpus classification
  ok: markdown shows separated statuses
progress_report selftest: OK
```

Synthetic H41 fixture used by selftest (rows): PASS×2, SKIP×1, NOT_COVERED×2, NOT_RUNNABLE×1, FAIL×1; unknown key `tbd_key` preserved. Per-file example: `DRSTR001.DAT PASS=1`; per-feature examples: `POIs PASS=1`, `roads SKIP=1`, `names NOT_RUNNABLE=1,FAIL=1`.

Synthetic H43 fixture used by selftest (targets): generated-fixture harness PASS (`tile_reader_gen`) => `firmware_proof:false,evidence_kind:harness_only,corpus_kind:generated_fixture`; generated-fixture explicitly marked firmware proof (`tile_reader_gen_fp`) => `firmware_proof:true`; synthetic probe => no firmware proof; factory `l3_claim` PASS => firmware proof; generated-fixture BLOCKED/NOT_RUNNABLE remain non-pass. Counts: generated-fixture targets 4, generated-fixture firmware proof passes 1, total firmware proof 2.

## Interpretation

- **FACT:** `progress_report.py` v3 + `progress_schema.py` accept legacy H26/H27 inputs and auto-detect/provisionally accept H41 matrix and H43 corpus JSON with unknown-key tolerance; `--json` documents schema version and field contract.
- **FACT:** H41 normalization separates PASS/FAIL/SKIP/NOT_COVERED/NOT_RUNNABLE and emits per-file/per-feature counts.
- **FACT:** H43 normalization separates corpus kinds and evidence kinds; generated-fixture harness/non-explicit results are not promoted to firmware proof; explicit non-synthetic firmware proof markers are honored; L4 emulator and L5 bench remain explicit/non-auto-pass.
- **HYPOTHESIS/TBD:** H41/H43 producer key names may still change. The contract is versioned (`osm2leaf.progress_report/v3`, provisional `l1l2_matrix/*` and `l3_corpus/*` input schemas) and tolerant so H42/H41/H43 can land without blocking on exact final names; producers should prefer the stable H41 row keys and H43 fields documented in `tools/progress_schema.py`.
- **UNKNOWN:** Real H41/H43 producer output shapes until H41/H43 land; workflow wiring (H42).

## Conclusion

H47 lands a minimal, testable schema contract before H42 wiring. Legacy progress inputs remain compatible; H41 per-file/per-feature matrix status separation and H43 generated-fixture corpus classification are machine-checkable from synthetic fixtures. Rule 13 is preserved: offline L1/L2 remains offline, generated-fixture L3 is reported separately, and only explicitly marked non-synthetic firmware-proof evidence can count as firmware proof. L4 (emulator, M8) and L5 (bench/car, M6) remain manual and never auto-pass.

## Mapping fields to rule 13 and L1-L5 (2026-11-09)

| Field / section | Level | Rule 13 / 2026-11-09 meaning | Allowed inference |
|---|---|---|---|
| `schema`, `schema_version`, `schema_contract` | report | Contract/version/field names for consumers; not evidence. | Parse/aggregate only. |
| `l1l2.kind=l1l2_legacy`, `summary`, `checks` | L1/L2 offline | Legacy H26 synthetic/fixture signal. | Offline format/structure signal only. |
| `l1l2.kind=l1l2_matrix`, `rows[].{level,file,feature,status,command,reason}`, `counts`, `by_file`, `by_feature` | L1/L2 offline (generated fixture) | H41 per-file/per-feature generated-fixture signal. `SKIP/NOT_COVERED/NOT_RUNNABLE` separated from `PASS`. | Progress/regression signal only; never firmware/L3/L4/L5 acceptance. |
| `l3.targets[].{status,synthetic,l3_claim,firmware_proof,evidence_kind,corpus_kind,ran_on_our_generated_data}` | L3 fragments | H43-aware corpus/evidence classification. `firmware_proof` only for explicitly marked non-synthetic PASS. | Firmware proof only when explicitly marked and non-synthetic; generated-fixture/synthetic/harness otherwise. |
| `l3.generated_fixture_*`, `l3.by_corpus_kind`, `l3.by_evidence_kind` | L3/reporting | Distinguishes synthetic/vendor/factory/generated-fixture corpora and harness-only vs firmware-proof evidence. | Prevents H42 misclassification; not acceptance by itself. |
| `l4_emulator.stages[].status/evidence` | L4 full-system emulator (M8) | Manual/bounded emulator acceptance state. No auto-pass. | L4 acceptance only with explicit recorded evidence. |
| `l5_car.stages[].status/evidence` | L5 bench/car (M6) | Manual bench/car acceptance state. No auto-pass. | Final acceptance only with explicit recorded evidence (EXP/photo/log). |

## Reproduction

```bash
python3 tools/progress_report.py --selftest
python3 tools/progress_report.py --json /tmp/opencode/h47-progress.json --md /tmp/opencode/h47-progress.md --no-stdout
python3 - <<'PY'
import json
r=json.load(open('/tmp/opencode/h47-progress.json'))
assert r['schema']=='osm2leaf.progress_report/v3'
assert r['schema_contract']['l1l2_matrix_input']
assert r['schema_contract']['l3_corpus_input']
assert r['separation']['generated_fixture_l3_evidence']
print('ok')
PY
```

## Follow-ups

- [ ] H42: wire `progress_report.py` v3 into CI artifacts/job summaries, consuming H41/H43 producer JSON when available.
- [ ] H41/H43: when final key names land, update `tools/progress_schema.py` provisional mappings/TBD notes and add producer-shaped fixtures; keep unknown-key tolerance.
- [ ] H27: if a real non-synthetic `firmware_proof`/`l3_claim` PASS appears, verify dashboard/report counts it correctly across legacy and corpus-aware inputs.
- [ ] Revisit schema if H41 needs multi-fixture baselines or H43 needs per-artifact provenance hashes beyond current fields.
