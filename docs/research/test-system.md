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
does not invent hidden behavior.

| Component | Level / role | Command / interface (observed) | Fixture / data scope | Evidence / notes |
| --- | --- | --- | --- | --- |
| `tools/selftest.py` | Test infra | `python3 tools/selftest.py [--json] [--only ...]` | Synthetic/tool-local; discovers tools with `--selftest` | Hard gate in `.github/workflows/ci.yml` on Py 3.11/3.13. **SKIP is not PASS** (workflow README/policy). |
| `tools/claims_check.py` | Board/ledger hygiene | `python3 tools/claims_check.py` | Repo text (`docs/research/claims.md` and references) | Hard gate in `ci.yml`. |
| `tools/todo_check.py` | Board hygiene | `python3 tools/todo_check.py TODO.md` | Repo text | Hard gate in `ci.yml`; errors fail, warnings reported (workflow). |
| `tools/cardcheck.py` | L1 | `python3 tools/cardcheck.py (--image IMAGE \| --root ROOT) [--json ...] [--partial] ...` (help) | Card image or extracted root; local/vendor when supplied | Used by local verification ladder and referenced by L1/L2 fixtures. No vendor data in CI. |
| `tools/l2check.py` | L2 | `python3 tools/l2check.py --root ROOT [--profile PROFILE] [--json ...] [--no-golden] [--cmp-limit N] [--no-tiles] ...` (help) | Extracted card root; golden profiles in `tools/golden/*` where applicable; local/vendor or suitable fixture | Semantic/golden ladder; `--update-golden` only after intentional decoder change (AGENTS). |
| `tools/cmpind.py` | L1/L2 primitive | `python3 tools/cmpind.py verify REFER001` etc. (AGENTS) | `.cmp/.ind` pairs; local/vendor or synthetic fixtures | Primitive/structural `.cmp/.ind` checks. |
| `tools/l1l2_fixtures.py` | L1/L2 fixture matrix (H26) | `python3 tools/l1l2_fixtures.py [--json PATH] [--md PATH] [--selftest]` (help) | **Synthetic/generated only, no vendor data.** NOT COVERED cases reported, never PASS. | Blocking on Py 3.11/3.13 in `.github/workflows/l1l2-fixtures.yml`; Py 3.14 informational (H9/zlib-ng context). Rule 13: offline only. |
| `tools/l3check.py` | L3 / card gate (M9.8/M9.12) | `python3 tools/l3check.py [--build-corpus] [--card CARD --factory FACTORY] [--json] [--selftest] ...` (help). Exit codes observed: 0 runnable pass, 1 fail/invalid, 2 usage, 3 nothing runnable / no runnable verdict in relevant modes. | Synthetic corpus (`--build-corpus`); card/factory images are **local/vendor** inputs (not CI PR). | `--card` is M9.12 software gate direction; S0/S1 no-diff baseline verdict gap tracked by M9.12/M9.31 (TODO/claims context). Synthetic PASS is not firmware proof. |
| `tools/progress_report.py` | Dashboard (H27) | `python3 tools/progress_report.py [--json] [--md] [--l1l2-json] [--l3-json] [--l5-status] [--l4-status alias] [--l4-emulator-status] [--run-tools] [--selftest]` (help) | Reads repo files and supplied JSON/status inputs; no vendor data read by tool itself. | Schema `osm2leaf.progress_report/v1` (C-2770). Separates offline / L3 firmware proof / car(L5)-required/manual emulator(L4) states; synthetic L3 PASS not firmware proof (C-2771); L4/L5 not auto-passed (C-2772, help). |
| `tools/realcheck.py` | Local/vendor regression | `python3 tools/realcheck.py IMG256 [--selftest] ...` (help) | **Vendor IMG256** (or supplied image). Exit 2 = no image (AGENTS). | Pinned CE/real-byte checks; not a PR CI gate. |
| `tools/fetch_image.py` | Local/vendor acquisition | `python3 tools/fetch_image.py --image KEY [--part SIZE] -o PATH [--verify PATH] [--selftest]` (help) | Downloads pinned vendor images from `files.viaaq.eu` (AGENTS rule 11 context). | Enables "no image on this machine is not a blocker" for local work; **not** used to put vendor data in repo/PR CI. |
| `.github/workflows/ci.yml` | PR/push quality gate | Runs on `pull_request` and `push` to `main` (workflow) | No vendor data/images/QEMU/L4/L5. | Hard: `selftest --json`, `claims_check.py`, `todo_check.py` on Py 3.11+3.13. Informational: Py 3.14 (H9 zlib-ng context). |
| `.github/workflows/l1l2-fixtures.yml` | PR/push L1/L2 fixtures | Runs on `pull_request` and `push` to `main` (workflow) | No vendor data/golden EU2011 on real ROOT/full vendor REFER001/real LEV3456R. | Hard: `l1l2_fixtures.py` runnable checks on Py 3.11+3.13. Informational: Py 3.14. Artifacts: `l1l2.json`, `l1l2.md`. |
| `.github/workflows/README.md` | Policy doc | N/A | N/A | Documents hard/informational split, SKIP≠PASS, why no vendor data. |

**Interfaces/terminology note (no blocking contradiction found):** `progress_report.py`
help exposes both emulator and bench/manual status inputs (`--l4-emulator-status`
for M8, `--l5-status` for car/bench with `--l4-status` backward alias). This is
consistent with the 2026-11-09 mapping migration; historical C-2770 prose still
uses older "L4 car" wording in places — treat `progress_report` current flags
and this document's mapping as canonical for new work.

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

**Rule:** **`SKIP`, `NOT_COVERED`, `NOT_RUNNABLE`, `BLOCKED`, and `NOT_RUN` are
never `PASS`.** They must remain visible in summaries/artifacts so "green" does
not imply coverage or firmware/car acceptance.

## 5. Execution matrix

| Environment | Data / fixture policy | Allowed/proven levels | Typical jobs/commands | Not allowed / caveats |
| --- | --- | --- | --- | --- |
| **PR CI (no vendor)** | No vendor images, dumps, full card trees, `IMG256`, or secrets (`ci.yml`, `l1l2-fixtures.yml` READMEs/policies). Synthetic/generated fixtures only. | L1/L2 offline on synthetic fixtures; tool/ledger/board hygiene; future H28 synthetic L3 signal if landed. | `selftest --json`, `claims_check.py`, `todo_check.py`, `l1l2_fixtures.py --json/--md`; future synthetic L3/H42 artifacts. | No firmware acceptance claim (rule 13). No byte-identical vendor recompression claim. No QEMU build requirement in current PR gates. No L5. |
| **Local-only vendor** | Vendor images/card trees kept outside repo/`archive` ignored paths; never committed. Use `fetch_image.py`/local paths as needed. | L1/L2 on real trees/images, `realcheck.py`, local `l3check.py --card/--factory`/target runs, `cmpind.py`/`cardcheck.py`/`l2check.py` verification ladder. | `realcheck.py IMG256`, `cardcheck.py --image/--root`, `l2check.py --root`, `l3check.py --card ... --factory ...`, `fetch_image.py --verify`. | Results are evidence only when commands/inputs/hashes are recorded in EXPs; still not car acceptance. |
| **M8 L4 emulator** | Emulator/runtime artifacts as defined by M8; no vendor bytes in repo. Inputs/corpora must be policy-compliant. | L4 full-system emulator integration checks (QEMU `ze0`, M8). | M8 task commands/workflows when implemented; progress via explicit L4 emulator status (`progress_report --l4-emulator-status`). | **Not auto-PASS.** Hardware unavailable does not make L4 a substitute for L5 acceptance. |
| **L5 bench / manual (Marek)** | Real unit + real/spare cards; vendor/original card handling per safety rules. Bundles/manifests must not publish vendor images. | L5 bench/car acceptance protocol (S0–S3 in `card-test-plan.md`; recovery/abort criteria apply). | Manual run log + photos/logs + H29-generated checklist/manifest (planned). Record as explicit evidence/status. | **Manual only, hardware currently unavailable.** One variable per run. **Never auto-PASS** in dashboards/CI. |

## 6. Regression gate policy

**Hard (blocking) gates today (PR/push to `main`, no vendor):**
- `ci.yml`: `tools/selftest.py --json`, `tools/claims_check.py`,
  `tools/todo_check.py TODO.md` on Python 3.11 and 3.13. `FAIL` blocks.
- `l1l2-fixtures.yml`: `tools/l1l2_fixtures.py` runnable checks on Python 3.11
  and 3.13. `FAIL` of runnable checks blocks; `NOT_COVERED` is reported, not a
  pass/failure of covered runnable checks.

**Informational (non-blocking):**
- Python 3.14 matrix entries in both workflows (`continue-on-error`) due to
  zlib-ng/H9 behavior; they do **not** make byte-identical vendor recompression
  claims.

**Honest classification rules:**
- Tools without `--selftest` or with missing dependencies are classified by
  `selftest.py` policy as **SKIP** (not PASS); workflow summaries must preserve
  that distinction.
- `NOT_COVERED` / `NOT_RUNNABLE` / `BLOCKED` / `NOT_RUN` must not be promoted to
  green success.
- Synthetic L3 `PASS` may be reported as harness/pipeline evidence but must
  **not** be counted as firmware proof (rule 13 / C-2771 / H28 scope).
- L4 emulator and L5 bench results require explicit evidence/status inputs;
  dashboards must not auto-pass them.

**Planned regression/gate expansions (do not treat as implemented):**
- H28/H42/H43: richer CI artifacts/summaries and generated-fixture/L3 reporting
  (no vendor in PR path).
- H44/H29: machine-checkable **L5 readiness** manifests/checklists and manual
  result registration.
- M8: L4 emulator gates when the emulator path is runnable and policy-compliant.

## Contradictions / follow-ups observed

- `progress_report.py` and TODO/claim prose reflect an in-progress terminology
  migration (pre-2026-11-09 `L4=car` wording in some text vs current
  `L4=emulator`, `L5=car` plus `--l4-status` compatibility alias). This document
  resolves it by following the 2026-11-09 mapping and citing current tool flags;
  future edits to claims/docs should keep terminology consistent.
- H29 text is partly Polish in TODO; its scope is clear (L5/car artifact prep,
  no remote car control, no public vendor binaries). This doc records the
  normalized interpretation only.
