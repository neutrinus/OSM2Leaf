# EXP-2026-11-08-H25: GitHub Actions CI quality gate

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** `none (CI/tooling task; no vendor data, no firmware image)`
- **Tools:** `python 3.15.0` / `PyYAML` (local syntax check), `git`, `gh` (PR creation). Workflow runtime uses `actions/checkout@v4`, `actions/setup-python@v5` on `ubuntu-latest`. Repo tools exercised by the gate: `tools/selftest.py`, `tools/claims_check.py`, `tools/todo_check.py`.
- **Claims:** C-2750–C-2759 (H25 reserved block; no new ledger claim registered by this EXP beyond recording the gate design)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the repository get a deterministic GitHub Actions quality gate on PR/push to `main` that measures test-infrastructure health (parses, selftests, ledger/board consistency) without vendor data, without masking missing dependencies as PASS, and without claiming card/firmware acceptance?

## Hypothesis

none / exploratory (infrastructure task). **Falsifier:** the workflow requires vendor images/IMG256/full card trees/QEMU/L4, cannot be parsed as valid YAML, reports tools with no `--selftest`/missing deps as PASS, or makes Python 3.14 zlib-ng byte-identity behavior a hard blocking gate.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none` |
| SHA-256 | `n/a` |
| Offset(s) / VA(s) | `n/a` |
| Tool / version | local `python3 tools/selftest.py --json`, `python3 tools/claims_check.py`, `python3 tools/todo_check.py TODO.md` |
| Repo tool | `.github/workflows/ci.yml`, `.github/workflows/README.md` |

## Method

1. **Sample and hash.** No vendor/sample bytes. This task adds CI configuration and documentation only.
2. **Commands.** Runnable as written from repo root:

```bash
# Precheck (recorded state before H25 work in this worktree)
ls .github/workflows 2>&1 || true
python3 tools/selftest.py --list

# Local validation used for this EXP
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
python3 tools/selftest.py
python3 tools/claims_check.py
python3 tools/todo_check.py TODO.md
```

3. **Controls.** *Positive*: local `selftest.py` run reports explicit PASS/FAIL/SKIP counts and exits 0 only when failures are 0 (`passed=63 failed=0 skipped=18 total=81` observed on 2026-11-08 in this worktree); `claims_check.py` returns `claims_check: OK`; `todo_check.py` returns `todo_check: OK` with errors=0 (warnings present). *Negative*: the workflow is designed so a non-zero `selftest.py` / `claims_check.py` / `todo_check.py` (errors) step fails the job; Python 3.14 is isolated as informational (`continue-on-error`) rather than weakening the 3.11/3.13 hard gate.
4. **Scope.** Adds `.github/workflows/ci.yml` and `.github/workflows/README.md`; updates H25 task metadata in `TODO.md`. Does **not** download vendor data, touch `IMG256`, build QEMU, run L4, add secrets, or change selftest semantics in existing tools. Local validation was run in `/home/marek/projekty/OSM2Leaf-wt-H25` on branch `task/h25-ci-github-actions`; first GitHub Actions execution happens after push/PR.
5. **Falsifier.** A CI run that passes while a blocking check fails, or that requires vendor bytes to become green, refutes the gate. An environment-dependent selftest failure must be classified as SKIP with reason in the tool (not masked here); if that prevents an honest green gate, H25 becomes `blocked` with `Unblock:` per task Stop.

## Observations

- Precheck: `.github/workflows` absent before H25; `selftest.py --list` worked.
- `python3 tools/selftest.py` (2026-11-08, local): `passed=63 failed=0 skipped=18 total=81 time=15.16s`, `selftest: OK`, exit 0. `selftest.py --json` reports tools without `--selftest` as `SKIP` (`detail: "no --selftest"`).
- `python3 tools/claims_check.py`: `duplicate claim IDs: 0`, `unregistered proposed claims: 0`, `bad annotations: 0`, `claims_check: OK`.
- `python3 tools/todo_check.py TODO.md`: `220 tasks, 0 error(s), 254 warning(s)`, `todo_check: OK`, exit 0.
- Workflow YAML parsed successfully with `PyYAML` locally (`YAML OK`).
- Draft PR: https://github.com/neutrinus/OSM2Leaf/pull/133 (`[H25] CI quality gate`, branch `task/h25-ci-github-actions`).
- CI run link: pending first GitHub Actions execution for PR #133 / pushes to the branch; inspect Actions tab for workflow `CI quality gate` (`.github/workflows/ci.yml`). This EXP records the gate definition and local preflight; the authoritative pass/fail signal is the GitHub Actions run.

## Interpretation

- **FACT:** The repository now contains a valid workflow definition that runs `selftest.py`, `claims_check.py`, and `todo_check.py` on PR/push-to-main without vendor data inputs.
- **OBSERVED:** Local preflight checks all pass with explicit SKIP reporting from `selftest.py`; `todo_check.py` has warnings but zero errors.
- **HYPOTHESIS:** GitHub-hosted runners will classify the same checks green on 3.11/3.13; any environment-specific instability (external binaries, disk) should surface as honest SKIP/FAIL and be handled per H25 Stop.
- **UNKNOWN:** Actual GitHub Actions run URL/status at the moment of this commit; 3.14 behavior under hosted `zlib-ng` for all current selftests.

## Conclusion

H25 adds a hard, vendor-data-free CI quality gate for test infrastructure: selftests/ledger/board consistency on Python 3.11+3.13, with Python 3.14 informational due to H9/zlib-ng. It does not move any format to L3/L4 acceptance and does not claim firmware/card readability. Follow-up evidence is the first GitHub Actions run for PR #133.

## Reproduction

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"
python3 tools/selftest.py
python3 tools/claims_check.py
python3 tools/todo_check.py TODO.md
# After push/PR: open https://github.com/neutrinus/OSM2Leaf/pull/133 Actions/checks
```

## Follow-ups

- [ ] Record the first green GitHub Actions run URL in PR #133 / follow-up note if needed (evidence, not a claim).
- [ ] If any selftest fails on GHA due to missing external deps, make that selftest/tool report `SKIP` with reason and file/block per H25 Stop.
- [ ] H26: extend CI with synthetic L1/L2 fixtures (separate task).
