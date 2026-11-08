# EXP-2026-11-08-H27: L1–L4 progress dashboard (reader-coverage + CI/tool results)

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** `none (tool-only task; aggregates repo files and tool JSON, no vendor data)`
- **Tools:** `python 3.15.0a5` / `zlib 1.3.1.zlib-ng` (local). Repo tools used: `tools/progress_report.py` (new, `--selftest`), `tools/l1l2_fixtures.py` (H26), `tools/l3check.py --build-corpus` (M9.8), `tools/claims_check.py`. Inputs read (repo, no vendor): `docs/research/reader-coverage.md`, `docs/research/claims.md`, `TODO.md`, `docs/research/card-test-plan.md`.
- **Claims:** C-2770–C-2779 (H27 reserved block)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can one dashboard artifact show progress toward "SD card readable by the car" as layer state — L1/L2 offline (runnable), L3 firmware/L3 (target verdicts, reader VAs/targets), L4 (S0–S3, manual/bench) — by aggregating existing sources of truth, without parsing unstable inputs heuristically, without vendor data, and without promoting L2 to L3/L4 or auto-passing L4?

## Hypothesis

none / exploratory (tooling/reporting task). **Falsifier:** the dashboard reports a synthetic L3 PASS as firmware proof, promotes L1/L2 to L3/L4, auto-passes any L4 stage without explicit recorded evidence, requires vendor data to run `--selftest`/produce a no-vendor report, or silently guesses when `reader-coverage.md` does not match its declared contract.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` |
| SHA-256 | `n/a` |
| Offset(s) / VA(s) | `n/a` |
| Tool / version | `python3 tools/progress_report.py`, `tools/l1l2_fixtures.py`, `tools/l3check.py` (pysh4, `--build-corpus`) |
| Repo tool | `tools/progress_report.py` (`schema osm2leaf.progress_report/v1`) |

## Method

1. **Sample and hash.** No vendor/sample bytes. `--selftest` uses synthetic JSON/Markdown fixtures and temp files; the example report reads only committed repo files and tool JSON generated from `--build-corpus` / `l1l2_fixtures` (no vendor data).
2. **Commands.** Runnable as written from repo root:

```bash
# New tool selftest (no vendor data)
python3 tools/progress_report.py --selftest

# Produce L1/L2 + L3 JSON inputs (no vendor data)
python3 tools/l1l2_fixtures.py --json /tmp/opencode/h27-l1l2.json --md /tmp/opencode/h27-l1l2.md --no-stdout-md
python3 tools/l3check.py --build-corpus --json > /tmp/opencode/h27-l3.json

# Dashboard artifact from stable JSON contracts + repo sources
python3 tools/progress_report.py \
  --l1l2-json /tmp/opencode/h27-l1l2.json \
  --l3-json /tmp/opencode/h27-l3.json \
  --json /tmp/opencode/h27-progress.json \
  --md /tmp/opencode/h27-progress.md --no-stdout

# Sanity checks (values observed in this EXP)
python3 -c "import json; r=json.load(open('/tmp/opencode/h27-progress.json')); print(r['reader_coverage']['row_count'], r['l3']['firmware_proof_passes'], [s['status'] for s in r['l4']['stages']], len(r['problems']))"
# expected: 30 0 ['NOT RUN', 'NOT RUN', 'NOT RUN', 'NOT RUN'] 0

# Gates
python3 tools/progress_report.py --selftest
python3 tools/claims_check.py
```

3. **Controls.** *Positive*: `--selftest` feeds known-good synthetic l1l2/l3/reader-coverage/TODO/L4 inputs and asserts the report separates layers, contains the rule-13/layer phrases, parses 30 reader-coverage rows, and is JSON-serializable. A real `l3check --build-corpus` report (1 synthetic PASS, 5 BLOCKED) is normalized so `firmware_proof_passes=0`. *Negative*: a synthetic L3 PASS (`synthetic=true`, `l3_claim=false`) is asserted **not** counted as firmware proof; `firmware_acceptance_claim=true` in an L1/L2 input is flagged as a problem; an L4 `PASS` without explicit evidence is demoted to `NOT RUN` and reported; an unreadable/mismatched reader-coverage header produces `problems` and does not guess row data.
4. **Scope.** Aggregates: L1/L2 from `l1l2_fixtures` JSON (H26 schema, stable), L3 from `l3check --json` (M9.8 schema, stable), reader-coverage main matrix from `docs/research/reader-coverage.md` under an explicit contract (header prefix `| # | File type / path |`, 12 leading columns in fixed order, rows until blank/non-table line; mismatch => `problems`, never guess), bounded L4 task lookup in `TODO.md` for M5.13b/M6.2/M6.5/M6.6/M6.7 plus optional explicit `--l4-status` JSON, and bounded claims counts from `claims.md` (counts only; `claims_check` remains authoritative). **Excluded:** GitHub Pages/external service; modifying `reader-coverage.md`; parsing arbitrary TODO prose heuristically; vendor data; auto L4 verdicts; promoting L2 to L3/L4.
5. **Falsifier.** Any of: synthetic L3 pass counted as `firmware_proof`; L4 stage auto-passed with no evidence; dashboard output implying L1/L2 == firmware/car acceptance; reader-coverage contract mismatch accepted silently; or `--selftest` requiring network/vendor bytes.

## Observations

Local run (2026-11-08, no vendor data):

```text
progress_report --selftest: OK (26 checks)
l1l2_fixtures: runnable 6P/0F/1S, not_covered=2, verdict=OK
l3check --build-corpus --json: schema osm2leaf.l3check/v1, result PASS, 6 targets (1 PASS synthetic, 5 BLOCKED)
progress_report: reader-coverage rows=30, l3 firmware_proof_passes=0,
  L4=['NOT RUN','NOT RUN','NOT RUN','NOT RUN'], problems=0
claims_check.py: OK (0 duplicate IDs, 0 unregistered proposed claims)
```

Reader-coverage aggregate (from `docs/research/reader-coverage.md`, 30 rows, contract ok): `writer/gen` = generate_exists 4, generate_partial 4, generate_none 9, copy 12, absent 1; `firmware_reader` = located 3, partial 4, unlocated 9, not_needed 12, other 2; `L3 matrix` = blocked 6, planned 6, pass_firmware 0, gap 6, not_applicable 12.

L3 (from `l3check --build-corpus`): `probe-zlib-cmf` PASS but `synthetic=true`, `l3_claim=false` => **not** firmware proof; `hddinfo_compare`, `cmp_ind_reader`, `tile_reader`, `drstr_parser`, `mapcode_comparator` BLOCKED. Firmware proof passes = 0.

L4: prerequisite `M5.13b` done (S1/S2 test cards built); `M6.2` S0 open, `M6.5` S1 open, `M6.6` S2 open, `M6.7` S3 open — all reported **NOT RUN** (manual).

## Interpretation

- **FACT:** `tools/progress_report.py` generates `progress.json`/`progress.md` (schema `osm2leaf.progress_report/v1`) aggregating L1/L2 JSON, L3 JSON, reader-coverage matrix, bounded TODO/claims signals, and explicit L4 status, with no vendor data. It parses `reader-coverage.md` only under a declared table contract and reports problems instead of guessing.
- **OBSERVED:** The example report cleanly separates offline (L1/L2 runnable 6P/0F/1S, not firmware acceptance), firmware/L3 (0 firmware-proof passes; 1 synthetic PASS explicitly not proof; 5 BLOCKED), and car-required L4 (S0–S3 NOT RUN, M5.13b prereq done). Reader-coverage aggregate shows 3 located / 4 partial / 9 unlocated readers and 0 firmware-pass L3 matrix cells.
- **HYPOTHESIS:** As H25/H26 produce stable CI artifacts, wiring `progress_report.py` as a job-summary/artifact step will give PR/main a consistent progress view without changing source-of-truth files.
- **UNKNOWN:** Future reader-coverage table edits could violate the declared contract; the tool will report `problems` (and the EXP requires updating the contract before heuristic parsing).

## Conclusion

H27 delivers a reproducible, no-vendor-data L1–L4 dashboard that treats `reader-coverage.md`/`claims.md`/`TODO.md`/tool outputs as sources of truth and aggregates them without promoting L2 to L3/L4. The L3 layer is counted as firmware proof only for non-synthetic `l3_claim` PASS targets (currently 0); the synthetic `probe-zlib-cmf` PASS is visible but explicitly non-proof. L4 remains explicit manual status (NOT RUN/PASS/FAIL with evidence), never auto-passed.

## Mapowanie pól na regułę 13

| Report field / section | Layer | Reguła 13 meaning | Allowed inference |
|---|---|---|---|
| `l1l2.*`, "Udowodnione offline" | L1/L2 | Offline format/structure signal; necessary, not sufficient | "synthetic/round-trip checks pass/fail offline" — never firmware/car acceptance |
| `l3.targets[].status==PASS && !synthetic && l3_claim` / `firmware_proof_passes` | L3 | Firmware reader executed and accepted per target contract | firmware/L3 proof for that target only |
| `l3.targets[].synthetic==true` or `l3_claim==false` PASS | harness/pipeline | Runner/dispatcher path proof, not firmware acceptance | never counted as firmware proof |
| `l3.targets[].status==BLOCKED/SKIP` | L3 unknown | No verdict claimed | no acceptance, no rejection |
| `reader_coverage.summary.firmware_reader/l3_matrix` | aggregate source | Matrix state (reader located/planned/blocked), not a new proof | prioritization/coverage; proof requires cited VAs + L3/M8 evidence |
| `l4.stages[].status`, "Wymaga auta" | L4 | Car/bench acceptance; manual only | final acceptance only with explicit recorded evidence (EXP/photo/log) |

## Example report excerpt (generated, no vendor data)

```text
# H27 progress dashboard (L1–L4)
- schema: `osm2leaf.progress_report/v1`
- **Rule 13 / ladder:** ten raport rozdziela warstwy i nigdy nie podnosi L2 do L3/L4.

## Udowodnione offline (L1/L2)
- verdict: **OK** (runnable 6P/0F/1S, not_covered=2)

## Udowodnione przez firmware / L3 (tylko realne, nie syntetyczne)
- firmware proof passes: **0** · synthetic passes (not firmware proof): 1
| probe-zlib-cmf | synthetic | **PASS** | True | False | False |
| hddinfo_compare/cmp_ind_reader/tile_reader/drstr_parser/mapcode_comparator | ... | **BLOCKED** | False | False | False |

## Wymaga auta (L4, ręczne)
| S0 | M6.2 | **NOT RUN** | ...
| S1 | M6.5 | **NOT RUN** | ...
| S2 | M6.6 | **NOT RUN** | ...
| S3 | M6.7 | **NOT RUN** | ...
```

## Reproduction

```bash
python3 tools/progress_report.py --selftest
python3 tools/l1l2_fixtures.py --json /tmp/opencode/h27-l1l2.json --md /tmp/opencode/h27-l1l2.md --no-stdout-md
python3 tools/l3check.py --build-corpus --json > /tmp/opencode/h27-l3.json
python3 tools/progress_report.py --l1l2-json /tmp/opencode/h27-l1l2.json --l3-json /tmp/opencode/h27-l3.json --json /tmp/opencode/h27-progress.json --md /tmp/opencode/h27-progress.md --no-stdout
python3 -c "import json; r=json.load(open('/tmp/opencode/h27-progress.json')); assert r['l3']['firmware_proof_passes']==0; assert all(s['status']=='NOT RUN' for s in r['l4']['stages']); print('ok')"
```

## Follow-ups

- [ ] Wire `progress_report.py` into H25/H26/optional L3 workflows as a job summary + JSON/MD artifact (keeps sources of truth unchanged).
- [ ] If `reader-coverage.md` table format changes, update the explicit contract and selftest fixtures in the same PR (no heuristic fallback).
- [ ] When a real non-synthetic L3 target reaches `l3_claim` PASS, verify the dashboard counts it as firmware proof and cites the target/claims.
- [ ] When Marek records S0–S3 outcomes, accept them only via explicit `--l4-status` evidence/EXP linkage; never auto-promote.
