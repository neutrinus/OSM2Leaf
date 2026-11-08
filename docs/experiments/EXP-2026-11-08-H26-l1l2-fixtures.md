# EXP-2026-11-08-H26: L1/L2 synthetic/generated fixture CI pipeline

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** `none (tooling/CI task; fixtures are generated synthetically in-process, no vendor bytes committed or read)`
- **Tools:** `python3` (local run used Python 3.15.0a5 / zlib `1.3.1.zlib-ng` — H9: byte-identical recompress unverifiable on this host; the pipeline reports that as SKIP, not PASS). Repo tools exercised: `tools/l1l2_fixtures.py` (new), `tools/cardcheck.py`, `tools/drstr_ze0.py`, `tools/drstr.py`, `tools/cmpind.py`, `tools/cmpind_writer.py`, `tools/ze0-viewer/harness.py`, `tools/imgpatch.py`. CI workflow: `.github/workflows/l1l2-fixtures.yml` (Python 3.11/3.13 hard, 3.14 informational).
- **Claims:** C-2760 (C-2761–C-2769 reserved)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can we automatically measure, in CI and without vendor data, whether the offline L1/L2 layer accepts synthetically built/mutated structures — producing a per-check JSON/Markdown matrix whose exit code reflects only runnable checks — while never claiming firmware acceptance (rule 13)?

## Hypothesis

none / exploratory (infrastructure task). **Falsifier:** the pipeline reports PASS for a path with no synthetic fixture (fakes coverage), fails on NOT COVERED/SKIP-for-H9 cases that are not runnable failures, requires vendor data/ROOT/IMG256/full REFER001/LEV3456R-on-real-files, omits the required categories, or requires report-logic changes to add a new synthetic check (registry not data-driven).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` |
| SHA-256 | `n/a` |
| Offset(s) / VA(s) | `n/a` |
| Tool / version | `python3 tools/l1l2_fixtures.py`, `tools/cardcheck.py --help`, `tools/l2check.py --help`, `tools/selftest.py`, `tools/claims_check.py` |
| Repo tool | `tools/l1l2_fixtures.py` (`--selftest`, registry, JSON/MD matrix); `.github/workflows/l1l2-fixtures.yml` |

## Method

1. **Sample and hash.** No vendor/sample bytes. All fixtures are generated synthetically in-process by repo tools (cmpind/drstr/imgpatch selftests, temp-tree round-trips) or probed and classified NOT COVERED where no vendor-free fixture exists.
2. **Commands.** Runnable as written from repo root:

```bash
# Prechecks (H26)
python3 tools/cardcheck.py --help
python3 tools/l2check.py --help
python3 tools/mkcard.py --selftest
python3 tools/imgpatch.py --selftest
python3 tools/cmpind.py --selftest
python3 tools/cmpind_writer.py --selftest
python3 tools/drstr_ze0.py --selftest

# New tool
python3 tools/l1l2_fixtures.py --selftest
mkdir -p /tmp/opencode/h26
python3 tools/l1l2_fixtures.py --json /tmp/opencode/h26/l1l2.json --md /tmp/opencode/h26/l1l2.md --no-stdout-md

# Gates
python3 tools/selftest.py
python3 tools/claims_check.py
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/l1l2-fixtures.yml')); print('YAML OK')"
```

3. **Controls.** *Positive*: `l1l2_fixtures.py --selftest` verifies registry covers all 5 required categories, unique ids, data-driven fake-check addition, JSON/MD generation, `firmware_acceptance_claim=false`/`vendor_data_used=false`, and exit semantics (`FAIL` runnable => non-ok; `SKIP`/`NOT COVERED` do not fail). A real run executes synthetic checks and returns verdict OK when no runnable check fails. *Negative*: selftest injects a fake `FAIL` and asserts verdict false/non-zero semantics; injects invalid status normalized to `FAIL`; `NOT COVERED` excluded from runnable total. A check with no synthetic fixture is `NOT COVERED` (never PASS). `zlib-ng` recompress byte-identity is `SKIP (zlib-ng, H9)`, not PASS.
4. **Scope.** Measures offline L1/L2 on synthetic/generated fixtures only: `L1 synthetic` (attempt/probe — currently NOT COVERED because no vendor-free full ZE0 card builder exists for coherent DRSTR+MMAIN+tile level tables+common headers+REFER001/top-level structure), `L2 DRSTR` (drstr_ze0 selftest + build/parse round-trip on synthetic temp tree), `L2 cmp/ind` (cmpind/cmpind_writer selftests + preserved-stream round-trip + semantic recompress round-trip with H9 byte-identical SKIP on zlib-ng), `L2 tile` (harness selftest probed; NOT COVERED — requires tile arg/vendor fixture), `L2 POI mutation` (imgpatch selftest, synthetic). **Excluded (out of scope, never faked):** golden EU2011 on real `ROOT`, full 194 REFER001 pairs on vendor data, `--include-lev`/LEV3456R on real files, L3 firmware execution, L4 hardware.
5. **Falsifier.** Any runnable check that reads vendor bytes, any NOT COVERED reported as PASS, any H9 byte-identical claim on zlib-ng reported as PASS, or any runnable FAIL producing exit 0 refutes the pipeline's honesty/semantics.

## Observations

Local run (2026-11-08, this worktree, zlib runtime `1.3.1.zlib-ng`):

```text
l1l2_fixtures.py --selftest: OK (19 checks)
l1l2_fixtures: runnable 6P/0F/1S, not_covered=2, verdict=OK
```

Matrix (per required category):

| Category | Check | Status | Runnable | Command (summary) |
| --- | --- | --- | --- | --- |
| L1 synthetic | `l1.synthetic.cardcheck` | NOT COVERED | no | `cardcheck --root <synthetic-ze0-tree> --partial --fast` — no vendor-free full ZE0 card builder |
| L2 DRSTR | `l2.drstr.selftest` | PASS | yes | `drstr_ze0.py --selftest` |
| L2 DRSTR | `l2.drstr.build-roundtrip` | PASS | yes | `drstr_ze0.build` + `drstr.parse` on synthetic temp tree |
| L2 cmp/ind | `l2.cmpind.selftest` | PASS | yes | `cmpind.py --selftest` |
| L2 cmp/ind | `l2.cmpind.writer-selftest` | PASS | yes | `cmpind_writer.py --selftest` |
| L2 cmp/ind | `l2.cmpind.preserve-roundtrip` | PASS | yes | `CmpFile.write` + `repack_preserve` (synthetic) |
| L2 cmp/ind | `l2.cmpind.recompress-roundtrip` | SKIP | yes | semantic round-trip OK; byte-identical SKIP (zlib-ng/H9) |
| L2 tile | `l2.tile.harness-selftest` | NOT COVERED | no | `harness.py selftest <tile>` requires tile fixture (no vendor-free path) |
| L2 POI mutation | `l2.poi.mutation.imgpatch-selftest` | PASS | yes | `imgpatch.py --selftest` (synthetic mutation/patch fixtures) |

Gates (local): `python3 tools/selftest.py` — 64 PASS / 0 FAIL / 18 SKIP (includes `l1l2_fixtures --selftest`). `python3 tools/claims_check.py` — OK. Workflow YAML parsed OK (`PyYAML`).

## Interpretation

- **FACT:** The repo now has a data-driven L1/L2 fixture runner and CI workflow producing JSON+Markdown matrix artifacts, with exit code driven only by runnable checks and explicit PASS/FAIL/SKIP/NOT COVERED per required category.
- **OBSERVED:** On a zlib-ng host, semantic recompress is measured and byte-identical recompress is SKIP (H9), so the pipeline remains honest without failing for an unverifiable byte-identity claim. L1 synthetic and L2 tile are NOT COVERED because current tools do not expose vendor-free fixtures for those specific paths.
- **HYPOTHESIS:** On GitHub-hosted Python 3.11/3.13 (stock zlib), the recompress check may PASS its full path (semantic; byte-identical handled per tool/runtime) and the hard gate will be green; 3.14 remains informational.
- **UNKNOWN:** First GitHub Actions run URL/status for `.github/workflows/l1l2-fixtures.yml` at commit time.

## Conclusion

H26 adds an offline, vendor-free L1/L2 measurement pipeline: 5 required categories are always reported, runnable failures fail the gate, and gaps are explicit NOT COVERED/SKIP entries — no firmware/L3/L4 acceptance is claimed. The main remaining offline gap is a synthetic ZE0 card builder sufficient for `cardcheck` L1 (MMAIN/tile/DRSTR coherence) and a synthetic tile fixture for harness selftest; adding either is a registry append, not report-logic change.

## Reproduction

```bash
python3 tools/l1l2_fixtures.py --selftest
python3 tools/l1l2_fixtures.py --json /tmp/opencode/h26/l1l2.json --md /tmp/opencode/h26/l1l2.md --no-stdout-md
# expected: verdict OK with runnable failures=0; categories include L1 synthetic, L2 DRSTR, L2 cmp/ind, L2 tile, L2 POI mutation
python3 tools/selftest.py
python3 tools/claims_check.py
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/l1l2-fixtures.yml')); print('YAML OK')"
```

## Follow-ups

- [ ] Record first green GitHub Actions run URL for `L1/L2 synthetic fixtures` workflow (evidence only).
- [ ] Add a vendor-free synthetic ZE0 card builder (coherent MMAIN/tile level tables + DRSTR + headers) and append an `L1 synthetic` runnable check.
- [ ] Add a vendor-free/synthetic tile fixture for `harness.py selftest` and append an `L2 tile` runnable check.
- [ ] Consider stock-zlib 3.13 runner evidence for byte-identical recompress path (H9); keep claims scoped to semantic round-trip unless byte identity is verified.
