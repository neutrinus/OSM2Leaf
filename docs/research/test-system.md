# Test system map (L1–L5)

> **Status:** living design map, 2026-11-09 (H46). This document maps the QA
> target — *generated SD card images the car would read* — to concrete tools,
> workflows, fixtures, status classes, execution environments, and TODO tasks.
> It does **not** add a new verifier, **not** change workflow code, and **not**
> claim firmware or car acceptance. Sources of truth remain
> [`AGENTS.md`](../../AGENTS.md), [`feedback-loop.md`](feedback-loop.md),
> [`reader-coverage.md`](reader-coverage.md),
> [`card-test-plan.md`](card-test-plan.md), `TODO.md`, `claims.md`, and tool
> results.

## 1. Level mapping L1–L5 (2026-11-09) and rule 13

The verification ladder follows `AGENTS.md` and
[`feedback-loop.md`](feedback-loop.md) mapping note
**2026-11-09 / Marek-PO decision**:

| Level | Name (current) | Meaning | Typical tools | Proves | Does not prove |
| --- | --- | --- | --- | --- | --- |
| L1 | Structural | Card/FAT/files/sizes/indexes/headers/containers consistent. | `tools/cardcheck.py`, parts of `tools/l1l2_fixtures.py`, `tools/cmpind.py verify`, `tools/drstr.py` checks | Broken/inconsistent card layout and declared structure | Wrong semantic content, firmware acceptance |
| L2 | Semantic / golden | Decode → model → compare with OSM/golden; round-trips byte-identical where required. | `tools/l2check.py`, `tools/l1l2_fixtures.py`, round-trip/golden checks | Offline semantic/format regressions on covered cases | Unit acceptance, unread format contract paths |
| L3 | Firmware fragments | Original firmware code fragments (decoder/decompressor/reader) run via harness/Ghidra/PySH4 on our data/corpora. | `tools/l3check.py`, `tools/l3_harness/*`, `targets.json`, `tools/chunk_decoder_l3.py` paths as wired | Misread format/field semantics on the exercised fragment path | Untouched code paths, full boot/app integration |
| L4 | Full-system emulator | Original software runs in an emulator (QEMU `ze0`, M8). | M8 tasks/workflows (planned/in progress in TODO); no vendor-emulator CI in PR gates today | Integration/file-open/error-screen paths the model can observe | Anything the model gets wrong; real hardware acceptance |
| L5 | Bench / car | The real unit boots the real card (M6). Expensive, one variable per run. **Hardware currently unavailable.** | Manual bench/car protocol in `card-test-plan.md`, M6 tasks, future H29 bundle tooling | SD lock/map-code/rendering/routing on real hardware (highest available oracle) | Electrical/analog edge cases, long-term wear |

**Mapping migration (explicit):** before 2026-11-09, some docs/tasks used
`L4 = bench/car` and `L5 = full-system emulator`. **After 2026-11-09,
`L4 = full-system emulator (QEMU/M8)` and `L5 = bench/car (M6)`.** Historical
EXPs/claims keep their original wording; interpret them with this mapping
(`feedback-loop.md`). Older prompt/task phrasing such as **"L4 readiness (bench
package)" maps to L5 readiness** under the current mapping. `H29` states this
alias explicitly for its v1 bundle naming (`prepare-L5-bundle`, alias
`prepare-L4-bundle`).

**Rule 13 (AGENTS.md / `reader-coverage.md` chain):** a file type we generate is
*confirmed* only when its firmware reader has a VA in `docs/format/` / evidence,
and *accepted* only when an L3 run (firmware fragment harness) or L4 full-system
emulator run reads our generated file and gets the expected values. L1/L2 and
round-trips are necessary, **not sufficient**. L5 remains the final acceptance
oracle when hardware is available.

## 2. Existing tools and workflows (command / fixture)

Only interfaces observed in repo files/help/workflows are listed; this section
does not invent hidden behavior. Each command is quoted from the workflow or
tool that prints it. **Shipped** means the command is on `origin/main` today,
not planned; the board status of the task that owns it is named where it
matters. `git show origin/main:TODO.md` (the board command quoted in `AGENTS.md`)
supplies every status quoted below.

| Component | Level / role | Command / interface (quoted from its source) | Fixture / data scope | Evidence / notes |
| --- | --- | --- | --- | --- |
| `tools/gate.py` | Standing gate (H85) — **shipped** | `python tools/gate.py --json gate.json` (`.github/workflows/ci.yml`, step "Standing gate"); `python3 tools/gate.py --selftest` (`tools/gate.py` usage); `python3 tools/board.py check HEAD` (`tools/gate.py` docstring, H121 row) | Repo text and committed snapshots; `archive/head256.img` is a vendor input that SKIPs the `fn_audit` row in CI. | The five rows are `selftest`, `claims_check`, `todo_check`, `board_check`, `fn_audit` (`tools/gate.py --json` prints them). Measured on this tree: `gate: 5 pass, 0 fail, 0 skip`. **SKIP is never PASS** (`.github/workflows/ci.yml` policy). |
| `tools/selftest.py` | Test infra — row **inside `gate.py`** | `python tools/selftest.py` (`.github/workflows/README.md`, gate table); `python3 tools/selftest.py --json` (`tools/selftest.py` usage) | Synthetic/tool-local; discovers tools with `--selftest` | Not a separate CI step any more: the `quality` job runs it via `gate.py` on Py 3.11/3.13; Py 3.14 informational (H9/zlib-ng). |
| `tools/claims_check.py` | Board/ledger hygiene — row inside `gate.py` | `python tools/claims_check.py --strict --count-check` (`.github/workflows/README.md`, gate table) | Repo text (`docs/research/claims.md` and references) | Run by `gate.py`; `--count-check` re-runs cited selftests (H78). |
| `tools/todo_check.py` | Board hygiene — row inside `gate.py` | `python tools/todo_check.py` (`.github/workflows/README.md`, gate table); `python3 tools/todo_check.py TODO.md` (`AGENTS.md`) | Repo text | Run by `gate.py`; errors fail, warnings reported. `--board-clean` runs `--strict` (red until H53). |
| `tools/fn_audit.py` | Firmware snapshot drift — row inside `gate.py` | `python tools/fn_audit.py archive/head256.img --corpus … --overlay …` (`.github/workflows/README.md`, gate table) | Committed corpus/overlay; real head is vendor-only | SKIPs in PR CI when `archive/head256.img` is absent; the separate H84 real-image workflow owns the real head. |
| `tools/cardcheck.py` | L1 | `python3 tools/cardcheck.py --root /path/to/root` (`tools/README.md`); `python3 tools/cardcheck.py --selftest` (`docs/experiments/EXP-2026-11-20-H103-cardcheck-fixture.md`); `--generate-fixture DIR`, `--generate-fixture-image IMG`, `--break KIND` (help) | Card image or extracted root; local/vendor when supplied; deterministic no-vendor fixture | Used by the local verification ladder and L1/L2 fixtures. **H104 is open**: no committed L1 `cardcheck` baseline yet. |
| `tools/l2check.py` | L2 | `python3 tools/l2check.py --root /path/to/root` (`tools/README.md`); `python3 tools/l2check.py --root /path/to/root --cmp-limit 20 --no-tiles` (`tools/README.md`); `python3 tools/l2check.py --selftest` (`tools/l2check.py` docstring) | Extracted card root; golden profiles in `tools/golden/*` where applicable | Semantic/golden ladder; `--update-golden PATH` (help) only after an intentional decoder change (AGENTS). |
| `tools/cmpind.py` | L1/L2 primitive | `python3 tools/cmpind.py verify REFER001` (`AGENTS.md`) | `.cmp/.ind` pairs; local/vendor or synthetic fixtures | Primitive/structural `.cmp/.ind` checks. |
| `tools/l1l2_fixtures.py` | L1/L2 fixture matrix (H26) | `python tools/l1l2_fixtures.py --json l1l2.json --md l1l2.md --no-stdout-md` (`.github/workflows/l1l2-fixtures.yml`); `python3 tools/l1l2_fixtures.py --require-covered` / `--selftest` (`tools/l1l2_fixtures.py` docstring) | **Synthetic/generated only, no vendor data.** NOT_COVERED cases reported, never PASS. | Blocking on Py 3.11/3.13; Py 3.14 informational (H9/zlib-ng). Rule 13: offline only. |
| `tools/l1l2_matrix.py` | L1/L2 per-file/per-feature matrix + baseline (H41/H57) — **shipped** | `python3 tools/l1l2_matrix.py --input matrix.json --check-baseline tools/fixtures/l1l2-matrix-baseline.json` (`tools/l1l2_matrix.py` usage; the workflow wraps it as `python tools/l1l2_matrix.py --input l1l2-matrix.json`, `--check-baseline tools/fixtures/l1l2-matrix-baseline.json` and `--no-stdout-md` (flags quoted from `.github/workflows/l1l2-fixtures.yml`)); `python3 tools/l1l2_matrix.py --selftest` / `--write-baseline PATH` (usage) | Rows keyed `level,file,feature` over the H40 generated fixture; committed baseline `tools/fixtures/l1l2-matrix-baseline.json` (12 rows, H57 EXP) | The second workflow step emits `l1l2-matrix.json`/`.md` and fails on a baseline regression. Key/`--check-baseline` are reused by H43 — no second schema. |
| `tools/l3check.py` | L3 / card gate (M9.8/M9.12) | `python3 tools/l3check.py --build-corpus --json l3.json` (`.github/workflows/ci.yml`, step "L3 check (synthetic corpus)"); `--card CARD`, `--factory FACTORY`, `--selftest` (`tools/l3check.py --help` flags) | Synthetic corpus (`--build-corpus`); card/factory images are **local/vendor** inputs (not CI PR). | Help prints exit codes 0 runnable pass, 1 fail/invalid, 2 usage, 3 nothing runnable / no runnable verdict. Measured: `pass 3 / fail 0 / skip 0 / blocked 10 / runnable 3 / total 13`, `result PASS`, `exit 0`, `corpus.entries 111`, `target_count 13` (this tree, `python3 tools/l3check.py --build-corpus --json l3.json`). Synthetic PASS is not firmware proof (rule 13); **H107 is open** on splitting the `blocked` bucket. |
| `tools/progress_snapshot.py` | One-command per-level snapshot (H56), used by H42 — **shipped** | `python3 tools/progress_snapshot.py --out artifacts/snapshot --json progress.json --md progress.md` (`.github/workflows/README.md`); `python3 tools/progress_snapshot.py --selftest` (`tools/progress_snapshot.py` usage) | Offline chain: `l1l2_fixtures.py` + `l1l2_matrix.py` + `l3check --build-corpus --json PATH` + `progress_report.py` (schema `osm2leaf.progress_report/v3` per README) | Exit propagated unchanged; `NO RUNNABLE TARGETS (RED)` is never a green SKIP. L4/L5 are `NOT RUN` unless explicit status JSON is supplied. |
| `tools/progress_report.py` | Dashboard (H27/H47) | `python3 tools/progress_report.py --selftest` / `--l1l2-matrix-json L1L2_MATRIX_JSON` / `--l3-corpus-json L3_CORPUS_JSON` / `--l4-emulator-status L4_EMULATOR_STATUS` / `--l5-status L5_STATUS` (help) | Reads repo files and supplied JSON/status inputs; no vendor data read by tool itself. | Schema `osm2leaf.progress_report/v3` (`SCHEMA` in `tools/progress_report.py`; README). H41/H43 inputs auto-detected; generated-corpus PASS is never promoted to firmware proof; L4/L5 never auto-passed. Historical C-2770 prose uses older "L4 car" wording — current flags and §1 mapping are canonical. |
| `tools/realcheck.py` | Local/vendor regression (H84 workflow) | `python3 tools/realcheck.py IMG256 --require-image` (`.github/workflows/firmware-regression.yml`); `python3 tools/realcheck.py IMG256` (workflow summary) | **Vendor IMG256** (or supplied image); exit 2 = no image without `--require-image`. | Manual/weekly only, not a PR CI gate; H84 is `done`. |
| `tools/fetch_image.py` | Local/vendor acquisition (H84 workflow) | `python3 tools/fetch_image.py --list` / `--image IMG256` / `--verify PATH` (`.github/workflows/firmware-regression.yml`) | Downloads pinned vendor images from `files.viaaq.eu` (AGENTS rule 11); head only in CI. | Enables "no image on this machine is not a blocker" for local work; never puts vendor data in repo/PR CI. |
| `tools/l4check.py` | L4 emulator one-command wrapper (M8.H13) | `python3 tools/l4check.py --card EUCARD --json` (`docs/experiments/EXP-2026-11-22-M8.H13-l4check.md`); `python3 tools/l4check.py --selftest` (`tools/l4check.py` docstring) | Needs a card, firmware head and `-M ze0` QEMU; `--selftest` is canned logs | Exit 3 (`NOT RUNNABLE`) is not a pass; not a standing `gate.py` check (rule 17 budget). L4 acceptance still needs a real run (rule 13). |
| `.github/scripts/main_watch.py` | Main-gate watchdog + PR-head sweep (H117/H126) — **shipped** | `python .github/scripts/main_watch.py --selftest` (`.github/workflows/main-watch.yml`); `python .github/scripts/main_watch.py --selftest` (`.github/workflows/main-watch.yml`), then the verdict steps with `--branch main`, `--workflow "CI quality gate"` / `"L1/L2 synthetic fixtures"`, `--limit 40` and `--prs` (flags quoted from the same workflow steps) | `gh run list` data (repo/token), plus committed replay fixtures | Each workflow classified on its own run list (M9.64); salient red opens a `[H117] fix:` issue, stale PR head a `[H126] fix:` issue, `cancelled` counted as de-dup. Both tasks are `done`. **H108 is open**: a mechanical `ci_audit.py` tip/step audit. |
| `tools/qemu-ze0/build.sh` | ze0 patch-series lint (M8.H14) — **shipped** | `bash tools/qemu-ze0/build.sh --selftest` / `--lint-patches` / `--check-version 11.1.3` (`.github/workflows/ci.yml`, `ze0-patches` job) | Pinned tarball cache (SHA-256 read from `build.sh`); no full QEMU build | Blocking job: a patch that no longer applies exits 4 and stays RED. CI gating only, not rule-13 acceptance. |
| `.github/workflows/ci.yml` | PR/push quality + L3 + patch series gate | Runs on `pull_request` and `push` to `main` (workflow) | No vendor data/images/QEMU build/L4/L5. | Blocking: `tools/gate.py` (Py 3.11/3.13), `python3 tools/l3check.py --build-corpus --json l3.json` (H28, Python 3.11), `build.sh` patch checks. Informational: Py 3.14. Artifact `l3-synthetic-corpus` (`l3.json`, `l3.txt`). |
| `.github/workflows/l1l2-fixtures.yml` | PR/push L1/L2 fixtures + baseline | Runs on `pull_request` and `push` to `main` (workflow) | No vendor data/golden EU2011 on real ROOT/full vendor REFER001/real LEV3456R. | Blocking: `l1l2_fixtures.py` runnable checks and the H41 matrix baseline step on Py 3.11/3.13. Informational: Py 3.14. Artifacts: `l1l2.json`, `l1l2.md`, `l1l2-matrix.json`, `l1l2-matrix.md`. |
| `.github/workflows/progress.yml` | PR/push progress dashboard (H42) — workflow **shipped**; task still `in progress` | `python3 tools/progress_snapshot.py --out artifacts/snapshot --json progress.json --md progress.md` (workflow step) | No vendor data in the PR path; local-only checks listed, never run. | Publishes `progress.json`/`.md`, `artifacts/snapshot/matrix.json`, explicit `NOT RUN` for L4/L5 and a local-only section; artifact `progress-h42`. |
| `.github/workflows/main-watch.yml` | Post-merge watchdog + PR sweep (H117/H126) | `workflow_run` + hourly `schedule` + `workflow_dispatch` (workflow) | `gh` run data only | Per-workflow verdicts, artifact `main-watch`. |
| `.github/workflows/firmware-regression.yml` | Manual/weekly IMG256 regression (H84) | `workflow_dispatch` + `schedule` (`cron: "23 4 * * 1"`) only — never `pull_request`/`push` (workflow) | Verified 256 MiB head from cache or rule-11 fetch | Runs `realcheck.py IMG256 --require-image`; explicit `SKIP (no image on this runner)`; artifact `img256-firmware-head-regression`. |
| `.github/workflows/README.md` | Policy doc | N/A | N/A | Documents hard/informational split, SKIP≠PASS, no vendor data, and the H41/H43/H84/H117 policies. |

**Open follow-ups named by the board (quoted from `origin/main:TODO.md`):**
H42 `in progress` (workflow shipped, task not closed), H43 `open` (generated-fixture
L3 corpus), H44 `open` (L5 readiness manifests), H57 `done` (baseline shipped),
H84 `done` (IMG256 workflow shipped), H104 `open` (L1 `cardcheck` baseline),
H107 `open` (split the L3 `blocked` bucket), H108 `open` (mechanical CI-tip audit).
The shipped artifacts/jobs above are not evidence that those open tasks are done.

## 3. Gap-closure dependency/order (H28,H29,H38,H40–H45,H47,M9.31)

This is a planning view from TODO/reader-coverage context; it does not change
task statuses.

| Task | Role in test system | Depends / coordinates (TODO) | Enables / unblocks |
| --- | --- | --- | --- |
| **H38** | Make `selftest.py` discover/run `tools/l3_harness` selftests | `—` (coordinates with H39) | Better CI/local visibility of harness health; supports honest SKIP/FAIL classification. |
| **H40** | Deterministic in-process no-vendor L1/L2 fixture + coherent ZE0 card/tree builder contract | `—` (coordinates with H41) | H41 matrix, generated-fixture regressions without vendor bytes. |
| **H41** | Per-file/per-feature L1/L2 progress matrix for generated card with regression baseline | H40; coordinates H42/H43 | Finer generated-card progress signal (roads/names/POIs/geometry). |
| **H47** | `progress_report` schema contract for H41/H43 shapes | H27 done; coordinate H41/H43; land before/with H42 wiring | Prevents H42 from guessing/misclassifying generated-fixture/L3 evidence. |
| **H43** | L3 generated-fixture corpus and per-reader progress for "our data" | H28, H40, H41, M9.12 and runnable M9 reader targets (TODO) | Extends H28 from synthetic-only to generated-fixture L3 evidence classification. |
| **H42** | Wire progress/dashboard and L1/L2/L3/L4-emu/L5-bench status into CI artifacts/job summaries (no vendor) | H25/H26/H27/H47 and relevant producer tasks (TODO context) | Visible, reproducible status reporting in CI without vendor data. |
| **H28** | L3 in CI: synthetic corpus, runnable/blocked targets, optional IMG256 mode | H25, M9.12/M9.20 state (adapts) | PR-safe L3 signal; optional firmware-head regression mode outside normal PR cost path. |
| **M9.31** | `l3check --card` baseline/no-diff verdicts for S0/S1 | M9.12 blocked; M9.11/M9.11b path | Unblocks M9.12 S0/S1 "all pass"/explicit verdict path instead of bare no-diff/no-runnable verdict. |
| **H44** | L5 bench/car readiness package validation in CI and local-only/vendor-image registry | H27/H29/M5.13b/M6.2 context (TODO) | Machine-checkable **L5 readiness** artifacts/checklists; no auto L5 verdict. |
| **H45** | `l3_precond` reachability gate for reopened L3 reader reruns | M1.12/M9.20/M9.24 context (TODO) | Rejects repeated L3 reruns with same M1.2f/import/binding blockers; produces `READY|BLOCKED|UNKNOWN`. |
| **H29** | Automate **L5** artifact preparation and result registration for S0–S3 (car/manual) | H27, M5.13b, M6.2/M6.5–M6.7 | One-command/workflow-dispatch bundle: what to flash/check/record; H27 can count L5 states machine-readably. No remote car control, no public vendor artifacts. |

**Suggested execution order (dependency-aware, not a schedule):**
1. H38 (harness visibility) and H40 (generated no-vendor fixture contract) — independent foundations.
2. H47 schema contract + H41 matrix design/implementation coordination (H47 should land before/with H42's wiring assumptions).
3. H28 synthetic L3 CI adaptation + M9.31 baseline/no-diff verdicts (both improve L3/card-gate signal; M9.31 targets M9.12 blocker).
4. H43 generated-fixture L3 corpus after H28/H40/H41/M9.12/runnable targets are ready.
5. H42 wires CI artifacts/summaries once H47 and producers are stable enough.
6. H44/H29 prepare/validate **L5 readiness** and manual result capture (hardware unavailable; no auto verdict). H45 is a safety gate for L3 reruns and can land whenever its inputs are stable.

## 4. Status classes and "never PASS" rule

Progress reporting must distinguish evidence quality. The test system uses these
classes (union across tool/reporting contexts; producers may emit a subset):

| Status | Meaning | May be treated as success? |
| --- | --- | --- |
| `PASS` | The check/target ran and met its explicit pass criteria. | Yes, **only within that check's level/scope**. |
| `FAIL` | The check/target ran and did not meet criteria. | No. |
| `SKIP` | Check not executed due to environment/policy/explicit skip (e.g. missing dependency, informational path). | **No — never PASS.** |
| `NOT_COVERED` | Case is outside current coverage/fixtures (reported intentionally). | **No — never PASS.** |
| `NOT_RUNNABLE` | No runnable target/implementation applies for this case/mode. | **No — never PASS.** |
| `BLOCKED` | Known dependency/blocker prevents a verdict (e.g. M1.2f, missing reader mapping, unavailable corpus). | **No — never PASS.** |
| `NOT_RUN` / `NOT RUN` | Manual/emulator/bench stage not executed (especially L4 emulator / L5 bench). | **No — never PASS.** |
| `NO_RUNNABLE` | `l3check` exit 3: no runner target produced a verdict (workflow labels it `NO RUNNABLE TARGETS`). Distinct from `SKIP` and from a `BLOCKED` target inside a runnable run. | **No — never PASS, never a green SKIP.** |

**Rule:** **`SKIP`, `NOT_COVERED`, `NOT_RUNNABLE`, `BLOCKED`, `NOT_RUN` and
`NO_RUNNABLE` are never `PASS`.** They must remain visible in summaries/artifacts
so "green" does not imply coverage or firmware/car acceptance.

**Where each token is produced (shipped sources):**
- `PASS`/`FAIL`/`SKIP (reason)` — `python3 tools/gate.py` (`tools/gate.py`
  docstring: "**PASS** -- the gate ran and exited 0", "**FAIL** -- the gate ran
  and exited non-zero for a reason other than a missing vendor input",
  "**SKIP (reason)** -- the gate could not run because a vendor input is
  absent"). A SKIP-only image gate still exits 0 with a named SKIP, never a
  silent pass.
- `PASS`/`FAIL`/`SKIP`/`NOT COVERED` — `python tools/l1l2_fixtures.py
  --json l1l2.json --md l1l2.md --no-stdout-md` (`.github/workflows/l1l2-fixtures.yml`
  prints `runnable {runnable_pass} PASS / {runnable_fail} FAIL /
  {runnable_skip} SKIP, not_covered=…`); `NOT COVERED` never fails a runnable
  check.
- `PASS`/`FAIL`/`SKIP`/`NOT_COVERED`/`NOT_RUNNABLE`/`BLOCKED`/`NOT_RUN` —
  `python3 tools/l1l2_matrix.py --input matrix.json --check-baseline
  tools/fixtures/l1l2-matrix-baseline.json` (`tools/l1l2_matrix.py` docstring);
  the five status tokens are explicit and never counted as PASS.
- `PASS`/`FAIL`/`BLOCKED`/`NO_RUNNABLE` — `python3 tools/l3check.py
  --build-corpus --json l3.json` (`.github/workflows/ci.yml` policy: exit 3
  stays RED; `BLOCKED` is counted, not a FAIL/PASS). `SKIP` here means an absent
  backend, not a missing vendor image (H28 policy step).
- `NOT RUN` — `python3 tools/l4_status.py` (`tools/l4_status.py --selftest`
  asserts the vocabulary is exactly `PASS|FAIL|BLOCKED|NOT RUN`); and
  `python3 tools/progress_snapshot.py --out artifacts/snapshot --json
  progress.json --md progress.md`, whose L4/L5 rows are readiness flags only.
- `salient`/`shadowed`/`cancelled`/`unrelated green` — `python3 .github/scripts/main_watch.py --branch main` (`.github/workflows/README.md`), with `--workflow "CI quality gate"` and `--limit 40` from `.github/workflows/main-watch.yml`. A `shadowed` or
  `unrelated green` covers nothing outside its own workflow; `cancelled` is a
  concurrency de-dup, not a green.

## 5. Execution matrix

| Environment | Data / fixture policy | Allowed/proven levels | Typical jobs/commands | Not allowed / caveats |
| --- | --- | --- | --- | --- |
| **PR CI (no vendor)** | No vendor images, dumps, full card trees, `IMG256`, or secrets (`ci.yml`, `l1l2-fixtures.yml` READMEs/policies). Synthetic/generated fixtures only. | L1/L2 offline on synthetic fixtures; tool/ledger/board hygiene; future H28 synthetic L3 signal if landed. | `selftest --json`, `claims_check.py`, `todo_check.py`, `l1l2_fixtures.py --json/--md`; future synthetic L3/H42 artifacts. | No firmware acceptance claim (rule 13). No byte-identical vendor recompression claim. No QEMU build requirement in current PR gates. No L5. |
| **Local-only vendor** | Vendor images/card trees kept outside repo/`archive` ignored paths; never committed. Use `fetch_image.py`/local paths as needed. | L1/L2 on real trees/images, `realcheck.py`, local `l3check.py --card/--factory`/target runs, `cmpind.py`/`cardcheck.py`/`l2check.py` verification ladder. | `realcheck.py IMG256`, `cardcheck.py --image/--root`, `l2check.py --root`, `l3check.py --card ... --factory ...`, `fetch_image.py --verify`. | Results are evidence only when commands/inputs/hashes are recorded in EXPs; still not car acceptance. |
| **M8 L4 emulator** | Emulator/runtime artifacts as defined by M8; no vendor bytes in repo. Inputs/corpora must be policy-compliant. | L4 full-system emulator integration checks (QEMU `ze0`, M8). | M8 task commands/workflows when implemented; progress via explicit L4 emulator status (`progress_report --l4-emulator-status`). | **Not auto-PASS.** Hardware unavailable does not make L4 a substitute for L5 acceptance. |
| **L5 bench / manual (Marek)** | Real unit + real/spare cards; vendor/original card handling per safety rules. Bundles/manifests must not publish vendor images. | L5 bench/car acceptance protocol (S0–S3 in `card-test-plan.md`; recovery/abort criteria apply). | Manual run log + photos/logs + H29-generated checklist/manifest (planned). Record as explicit evidence/status. | **Manual only, hardware currently unavailable.** One variable per run. **Never auto-PASS** in dashboards/CI. |

## 6. Regression gate policy

**Hard (blocking) gates on `origin/main` (PR/push to `main`, no vendor):**
- `.github/workflows/ci.yml`, `quality` job (Python 3.11 and 3.13): the single
  blocking step is `python tools/gate.py --json gate.json`. The workflow summary
  names it verbatim: "Hard gate (blocking): `tools/gate.py` (`selftest.py` +
  `claims_check.py --strict --count-check` + `todo_check.py` + `board.py check
  HEAD` + `fn_audit.py --corpus/--overlay`, one PASS/FAIL/SKIP policy) on Python
  3.11 and 3.13." A `FAIL` blocks; a SKIP (missing `archive/head256.img`) is
  listed and is never counted as PASS.
- `.github/workflows/ci.yml`, `l3` job (Python 3.11): the blocking step is
  `python3 tools/l3check.py --build-corpus --json l3.json` ("L3 policy (H28)"):
  "Blocking: `python3 tools/l3check.py --build-corpus --json l3.json` on the
  synthetic corpus; the tool exit is propagated (3 stays RED)." Artifact
  `l3-synthetic-corpus` (`l3.json`, `l3.txt`).
- `.github/workflows/ci.yml`, `ze0-patches` job: `bash tools/qemu-ze0/build.sh
  --selftest`, `bash tools/qemu-ze0/build.sh --lint-patches --patch-dir
  tools/qemu-ze0/patches` and `bash tools/qemu-ze0/build.sh --check-version
  11.1.3 \
     --srcdir "$HOME/.cache/qemu-ze0" \
     --patch-dir tools/qemu-ze0/patches` (workflow steps); exit 4 (a patch no
  longer applies) stays RED.
- `.github/workflows/l1l2-fixtures.yml`: `python tools/l1l2_fixtures.py --json
  l1l2.json --md l1l2.md --no-stdout-md` then the H41 matrix steps
  `python tools/l1l2_matrix.py --input l1l2.json` followed by `--json l1l2-matrix.json`, `--md l1l2-matrix.md`, `--no-stdout-md` (`.github/workflows/l1l2-fixtures.yml`) and
  `python tools/l1l2_matrix.py --input l1l2-matrix.json` followed by `--check-baseline tools/fixtures/l1l2-matrix-baseline.json` and `--no-stdout-md` (`.github/workflows/l1l2-fixtures.yml`) on Python 3.11/3.13.
  `FAIL` of runnable checks and baseline regressions block; `NOT COVERED` is
  reported, never a pass/failure of covered runnable checks.
- `.github/workflows/progress.yml` (H42): `python3 tools/progress_snapshot.py
  --out artifacts/snapshot --json progress.json --md progress.md` on Python
  3.11, exit propagated unchanged (rc=3 `NO_RUNNABLE` stays RED). Artifact
  `progress-h42`. The workflow is shipped; the task remains `in progress`.

**Post-merge and manual (not a PR gate, but shipped):**
- `.github/workflows/main-watch.yml`: `python .github/scripts/main_watch.py
  --selftest`, then `--branch main --workflow "CI quality gate" --limit 40`,
  the `L1/L2 synthetic fixtures` variant, and `--prs` (H126). Workflow dispatch
  and an hourly sweep; a salient red opens a `[H117] fix:` issue.
- `.github/workflows/firmware-regression.yml` (H84, `done`):
  `workflow_dispatch`/weekly `schedule` only; with a verified head runs
  `python3 tools/realcheck.py IMG256 --require-image`, with no head prints
  `SKIP (no image on this runner)`.

**Informational (non-blocking):**
- Python 3.14 matrix entries in `ci.yml` and `l1l2-fixtures.yml`
  (`continue-on-error`), because zlib-ng/H9 builds may diverge from stock zlib
  1.3.1 byte-identical behavior. They make no byte-identical vendor recompression
  claim.

**Honest classification rules (tool/workflow quotes):**
- `python3 tools/gate.py --selftest` proves the five-row policy with stubs:
  "exit 2 + missing-input message -> SKIP (not PASS)" and "a dropped claim row
  turns the board row FAIL". A gate's own exit code is not enough: `fn_audit`
  exits 2 for a missing head, which the runner classifies as SKIP only with a
  missing-input marker.
- `NOT_COVERED` / `NOT_RUNNABLE` / `BLOCKED` / `NOT_RUN` / `NO_RUNNABLE` must
  not be promoted to green success (`tools/l1l2_matrix.py`, `tools/l3check.py`
  and `tools/progress_snapshot.py` help/docstrings).
- Synthetic L3 `PASS` may be reported as harness/pipeline evidence but must
  **not** be counted as firmware proof (rule 13 / C-2771 / H28 scope).
- L4 emulator and L5 bench results require explicit evidence/status inputs;
  dashboards must not auto-pass them (`progress_report --l4-emulator-status`,
  `--l5-status`, with `--l4-status` as the backward alias).

**Committed no-vendor baseline (H57, `done`).** `tools/fixtures/l1l2-matrix-baseline.json`
is the committed expected result for the H40/H41 generated fixture, keyed by
`level,file,feature` (H57 Scope; H104 owns the separate L1 `cardcheck`
baseline, still `open`). The workflow's baseline gate is
`python tools/l1l2_matrix.py --input l1l2-matrix.json`, `--check-baseline tools/fixtures/l1l2-matrix-baseline.json` and `--no-stdout-md` (`.github/workflows/l1l2-fixtures.yml`), using the tool's documented
`python3 tools/l1l2_matrix.py --input matrix.json --check-baseline
tools/fixtures/l1l2-matrix-baseline.json` form. It fails (exit 1) when a baseline
PASS becomes FAIL/SKIP/NOT_COVERED or when a PASS key disappears from the
report; `SKIP -> FAIL` also fails (H57). A status rise (`FAIL -> PASS`,
`SKIP -> PASS`) is printed as an improvement, not an error; a new key is `NEW`,
a vanished non-PASS key is `DROPPED`, and a duplicated key is `DUPLICATE` — all
printed without failing the gate. SKIP/NOT_COVERED/NOT_RUNNABLE are never PASS.
Refresh the baseline only with an EXP/PR rationale (as for `l2check
--update-golden`), never to make a failing run pass;
`python3 tools/l1l2_matrix.py --input matrix.json --write-baseline PATH` writes
it and the diff of that file is the review record.

**Shipped vs open (board status quoted from `origin/main:TODO.md`):**
- Shipped: H28's blocking `l3check --build-corpus --json l3.json` job, H41/H57's
  per-file/per-feature matrix with the committed baseline, H84's
  workflow_dispatch/schedule IMG256 regression, H117/H126's watchdog and
  PR-head sweep, and the H42 `progress.yml` workflow.
- Still open: **H42** (task `in progress` — workflow shipped, not closed),
  **H43** (generated-fixture L3 corpus, `open`), **H44** (L5 readiness manifests,
  `open`), **H104** (L1 `cardcheck` baseline, `open`), **H107** (split the L3
  `blocked` bucket, `open`) and **H108** (mechanical CI-tip audit, `open`).
  H57 and H84 are `done`. A shipped job is not evidence that its owning task is
  closed.

**Planned expansions that are NOT shipped as of this refresh (do not treat as
implemented):** H43's generated-fixture L3 reporting in `progress.yml`, H44's
machine-checkable L5 readiness manifests/checklists, and M8's L4 emulator gates
beyond the `ze0-patches` lint/series job (rule 13; L4 acceptance requires a
real emulator run).

## L4 full-system emulator readiness (QEMU `ze0`, M8) — H110

This is the matrix row `prompt_qa.txt` asks for: **L4 full-system emulator
readiness — what can run, what is blocked.** It is *readiness*, not
acceptance (rule 13): a `PASS` below means the named stage's gate was met on
the named evidence, never that L4 accepts a generated card. The run itself is
**M8.E4** (full `Navi.exe` on a generated card); this table only says how far
the emulator has got and what each next stage waits on.

The machine is **QEMU `-M ze0`** built by `tools/qemu-ze0/build.sh` (default
pin 11.1.3 since M8.A11, C-6890; 8.2.10 before, C-4330); the boot orchestrator is `tools/qemu-ze0/run.sh`. The
panel is printed by `python3 tools/l4_status.py` (C-4410); every stage's
number below names the claim that carries it — none is retyped from TODO prose.
The full boot is wrapped by `python3 tools/l4check.py --card EUCARD --json`
(`docs/experiments/EXP-2026-11-22-M8.H13-l4check.md`; `tools/l4check.py` docstring
prints the form `python3 tools/l4check.py --card CARD.img [--head IMG256] [--qemu BIN]`),
which scores the DBGMSG log against these F0–F4 names plus F5 idle; exit 3 is
`NOT RUNNABLE`, never a pass. `feedback-loop.md` records that this is **not** a
standing `gate.py` check (rule 17 budget). The `tools/qemu-ze0/build.sh
--selftest` / `--lint-patches` / `--check-version 11.1.3` steps in
`.github/workflows/ci.yml` gate only the patch series, not an L4 run.

| Stage | Meaning | Gate it must meet | Evidence (claim) | Blocked by | Status without a run log |
| --- | --- | --- | --- | --- | --- |
| **F0** boot log | kernel exception log on one image | 0 CPU exceptions on a 10 s boot of one image | **C-4311** | — | `NOT RUN` (a boot log with `exceptions: 0` moves it to `PASS`) |
| **F1** stable kernel | `filesys.exe` + `device.exe` start, no unhandled fault | the two processes start and the kernel runs without a fault report | **C-1352** | — | `NOT RUN` |
| **F2** drivers | `filesys`/`device` load the driver set, boot not blocked | the driver set loads and no driver blocks boot | **C-1353** | **M8.C** | `NOT RUN` |
| **F3** SD mounted | the card's FAT partition mounts (`DSK1:`) | the FAT partition mounts, not `SD Check Error` | **C-1353** | **M8.C** | `NOT RUN` |
| **F4** `Navi.exe` headless | `Navi.exe` starts and reads map files, no error screen | M8.E4 done-when | **C-537** | **M8.A3, M8.A6, M9.16** | `NOT RUN` |
| **log** run-summary reader | `run.sh`'s printed keys parse | `tools/l4_status.py --selftest` proves the reader round-trips a summary | **C-4411** | — | `PASS` (self-test, no image needed) |

What the evidence rows say:

- **F0 (C-4311):** `run.sh --machine ze0` on the EU2011 head runs the full
  10 s wall clock with `exceptions: 0` and one unmodelled `write 0x38`; only
  the exception count and the access list are reproducible (a sampled PC is
  not a result). The machine skeleton builds (`build.sh --force`, `-M help`
  lists `ze0`) per **C-4310**; **C-4312** shows the access list is a
  `-M none` property and a CCN-modelling machine cannot reproduce it, which is
  why that clause was withdrawn, not failed.
- **F1 (C-1352):** with the `ze0-0006` patch the EU2011 kernel starts
  `filesys.exe` and `device.exe` and runs 839 s of guest time with no
  unhandled-exception report — the F1 milestone. The next layer is where it
  stops: the launcher's SD check fails, so F2/F3 are what remains (**C-1353**:
  the launcher stops at `AppLch > SD Check Error`, `Error Proc<00000080>`; no
  `gwes.exe`).
- **F4 (C-537):** the effort/feasibility row; F4 is months of board bring-up
  in the original estimate. Its entry chain is `M8.A3` and `M8.A6` (both
  `done`) plus **M9.16** (the L3 map-load chain) and the M8.E4 run itself, so
  the *one open software link* named on the board is M9.16.

How to read the panel (`python3 tools/l4_status.py`):

- **Without `--run-log`** every F-row status is `NOT RUN` (a missing key is
  never inferred — §4), and the readiness legend prints
  `F4 BLOCKED (M8.A3, M8.A6, M9.16)` (plus `F2 BLOCKED (M8.C)` and
  `F3 BLOCKED (M8.C)`). Status (`NOT RUN`) and readiness (`BLOCKED`) are
  separate facets: a stage can be blocked and not run at the same time.
- **With `--run-log WORK`** the tool reads only `run.sh`'s printed keys
  (`exceptions:`, `unmodelled register accesses (first-seen order):`,
  `final pc:`); `final pc` is carried for display and never scored. A clean
  log (`exceptions: 0`) moves **F0** to `PASS`; a non-zero count is an honest
  `FAIL`. Nothing else is promoted: `run.sh` prints no `filesys`/driver/FAT/
  `Navi.exe` evidence, so F1–F4 stay `NOT RUN` until their own evidence lands.
- **`NOT RUN` and `BLOCKED` are never `PASS`** (§4, §6). A `PASS` on this
  panel is only `F0`-with-a-clean-log; it is not an L4 acceptance claim.

This table replaces the four prose lines that used to live in TODO's critical
path and in the M8.A2 block; the TODO M8 section stays the task board.
`docs/research/full-system-emulation.md` §4 is the stage-effort reference and
its stage numbers are `HYPOTHESIS` (**C-537**), not measurements.

## Contradictions / follow-ups observed

- `progress_report.py` and TODO/claim prose reflect an in-progress terminology
  migration (pre-2026-11-09 `L4=car` wording in some text vs current
  `L4=emulator`, `L5=car` plus `--l4-status` compatibility alias). This document
  resolves it by following the 2026-11-09 mapping and citing current tool flags;
  future edits to claims/docs should keep terminology consistent.
- H29 text is partly Polish in TODO; its scope is clear (L5/car artifact prep,
  no remote car control, no public vendor binaries). This doc records the
  normalized interpretation only.
