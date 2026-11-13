# TODO history — 2026-11-13 (PO grooming archive)

Done tasks moved from `TODO.md` on 2026-11-13: completed (`Status: done`),
block no open/in-progress/blocked task's `Depends`, and completed on
`origin/main` before 2026-11-12 (more than 24 h). Commit dates on
`origin/main` are the authority. Earlier archives:
`todo-history-2026-11-05.md`, `-06.md`, `-09.md`.

## H (archived)

- [x] **H46 — Test system map: L1-L5 progress signal, fixtures, CI/local/L5 execution policy**
  - Status: done · Owner: task/h46-test-system-map · Critical: no · Pair: solo
  - Depends: H25, H26, H27 (existing artifacts to reference)
  - Goal: one living design doc that maps the QA target ("generated SD card images the car would read") to concrete tools/workflows/fixtures/tasks, so every agent can see what is proven offline, what is firmware/L3/L4-emulator proof, and what remains L5 bench/car/manual — without conflating levels.
  - Gap (QA 2026-11-09): workflows/tools exist (H25 `ci.yml`, H26 `l1l2_fixtures.py`/`l1l2-fixtures.yml`, H27 `progress_report.py`, M9.8 `l3check.py`) and planned tasks cover major holes (H28,H29,H38,H40-H45,M9.12/M9.31), but there is no single map of fixture strategy (synthetic vs generated no-vendor vs local-only vendor), regression policy, status classes, and execution split (PR CI / local vendor / M8 QEMU / L5 Marek). This causes ambiguous "progress" claims.
  - Scope: add `docs/research/test-system.md` (English). No code/workflow changes except optional cross-links. Level mapping must follow AGENTS/feedback-loop 2026-11-09: L1 structural, L2 semantic/golden, L3 firmware fragments, L4 full-system emulator (QEMU/M8), L5 bench/car (hardware unavailable). "L4 readiness (bench package)" wording from older prompts maps to **L5 readiness** under current mapping; state that explicitly.
  - Input: `AGENTS.md`, `docs/research/feedback-loop.md`, `docs/research/reader-coverage.md`, `docs/research/card-test-plan.md`, `.github/workflows/{ci.yml,l1l2-fixtures.yml,README.md}`, `tools/{selftest,cardcheck,l2check,l3check,progress_report,l1l2_fixtures,realcheck,fetch_image}.py` (interfaces), TODO tasks H25-H29,H38,H40-H45,H27,M9.8/M9.12/M9.31.
  - Done when: `test -f docs/research/test-system.md` and the doc contains sections/headings covering at least: (1) level mapping L1-L5 (2026-11-09) and rule 13, (2) existing tools/workflows with command/fixture, (3) gap-closure dependency/order for H28,H29,H38,H40-H45,H47/M9.31 as applicable, (4) status classes `PASS|FAIL|SKIP|NOT_COVERED|NOT_RUNNABLE|BLOCKED` and "SKIP/NOT RUNNABLE/BLOCKED never PASS", (5) execution matrix PR CI (no vendor) / local-only vendor / M8 L4 emulator / L5 bench-manual, (6) regression gate policy. `python3 tools/todo_check.py TODO.md && python3 tools/claims_check.py` still pass.
  - Stop: if task states or tool interfaces are contradictory, document the contradiction with file/task references and stop expanding claims; do not invent tool behavior.
  - Claims: C-3350–C-3359
  - Result: EXP-2026-11-09-H46-test-system-map.md (C-3350–C-3354); added `docs/research/test-system.md` mapping L1-L5 (2026-11-09, L4 emulator/L5 bench), rule 13, tool/workflow interfaces and fixtures, H28/H29/H38/H40-H45/H47/M9.31 gap order, status classes with never-PASS rule, execution matrix (PR CI no vendor/local vendor/L4 emulator/L5 manual), and regression gate policy. Noted terminology migration in `progress_report` (`--l4-emulator-status`, `--l5-status`, `--l4-status` alias) and older "L4 readiness (bench package)" => L5 readiness. `test -f` OK, `todo_check` OK (warnings pre-existing), `claims_check` OK, `selftest` 76 PASS/0 FAIL/15 SKIP.

- [x] **H47 — `progress_report` schema contract for H41 per-file/per-feature and H43 generated-L3 corpora**
  - Status: done · Owner: task/h47-progress-report-schema · Critical: no · Pair: solo
  - Depends: H27 (done). Coordinates with H41, H43, H42 (integration/wiring) — land before or with H42's progress wiring.
  - Goal: prevent H42 from guessing how to aggregate generated-fixture L1/L2 and generated-L3 progress; make the H27 `progress_report.py` input/output contract explicit and testable for new matrix shapes while preserving rule-13 separation.
  - Gap (QA 2026-11-09): `progress_report.py` consumes H26 `l1l2_fixtures` JSON and `l3check` JSON (help verified). H41 adds per-file/per-feature matrix with stable keys and regression baseline for a generated no-vendor fixture; H43 adds generated-fixture L3 corpus classification (`ran_on_our_generated_data`, synthetic/vendor/generated separation). Without a contract, H42 may duplicate logic or silently misclassify synthetic/harness results as firmware proof.
  - Scope: extend `tools/progress_report.py` (and/or add a tiny documented schema module, stdlib, named in PR) to accept H41/H43-compatible JSON via new/optional flags or auto-detected schema versions; emit `progress.json/md` fields that distinguish L1/L2 generated-fixture per-file/per-feature counts, L3 synthetic vs vendor/factory vs generated-fixture corpora, firmware-proof vs harness-only evidence, and L4 emulator (M8) / L5 bench (M6) manual states. No vendor data. No auto-PASS for L4/L5/manual.
  - Input: `tools/progress_report.py`, H27 schema/EXP, `tools/l1l2_fixtures.py` H26 JSON shape, `tools/l3check.py --json` shape, H41/H43 task specs (stable-key/field requirements), `.github/workflows` H42 needs.
  - Done when: `python3 tools/progress_report.py --selftest` covers (1) legacy H26/H27 inputs still parse, (2) a synthetic H41-style per-file/per-feature JSON fixture produces per-file/per-feature counts with `SKIP/NOT_COVERED/NOT_RUNNABLE` separated from PASS, (3) a synthetic H43-style generated-corpus L3 JSON is reported as generated-fixture evidence and not promoted to firmware proof unless explicitly marked, (4) L4 emulator and L5 bench manual states remain explicit/non-auto-pass. `--json` output documents schema version/field names. EXP maps fields to rule 13 and L1-L5 (2026-11-09).
  - Stop: if H41/H43 final key names are not yet fixed, land a minimal versioned contract (schema version + required keys + unknown-key tolerance) with synthetic fixtures and mark remaining keys `TBD` in EXP; do not block on implementation details of unfinished tasks.
  - Result: EXP-2026-11-09-H47-progress-report-schema (`tools/progress_report.py` v3 + `tools/progress_schema.py`; auto-detected H41 matrix/H43 corpus contract, backward-compatible legacy inputs, schema_contract in JSON; C-3360–C-3364).
  - Claims: C-3360–C-3369

- [x] **H48 — reader_precheck/M1.12: import or delegate to `sh4scan` (unblocks M3.19 done-when)**
  - Status: done · Owner: task/h48-sh4scan-reader-precheck · Critical: no · Pair: solo
  - Depends: — (M3.19 blocked on this)
  - Goal: satisfy M3.19’s done-when clause “M1.12 imports it rather than duplicating the scan” without duplicating `sh4scan`’s scan engine, or record an explicit board/TL amendment of that clause with rationale.
  - Precheck: `python3 tools/sh4scan.py --selftest` passes; confirm `tools/reader_precheck.py` is the M1.12 precheck tool referenced by TODO and that it does not import/delegate to `sh4scan` (baseline).
  - Scope: `tools/reader_precheck.py` (and only files required for the integration) — import or delegate to `tools/sh4scan.py` for overlapping pattern/anchor scan functionality where appropriate; **or**, if integration is not the right design, add an explicit board/TL decision record amending M3.19’s M1.12-import done-when clause (citing rationale) and update M3.19 accordingly. One task per PR.
  - Input: `tools/reader_precheck.py`, `tools/sh4scan.py`, TODO M3.19 done-when/Result/Blocker, EXP-2026-11-08-M3.19-sh4scan addendum 2026-11-09.
  - Done when: either (a) `python3 -c "import ast, pathlib; s=pathlib.Path('tools/reader_precheck.py').read_text(); assert 'sh4scan' in s"` (or an equivalent documented delegation) and `python3 tools/reader_precheck.py --selftest` / `python3 tools/sh4scan.py --selftest` pass with an EXP noting what overlaps were delegated; **or** (b) a board/TL decision is recorded (TODO/EXP/claims as appropriate) explicitly amending M3.19’s M1.12-import clause with rationale. In either case, when this PR merges it sets M3.19 `Status` back to `open` (or `done` only if clause (b) makes M3.19’s remaining done-when satisfied and documented) per rule 15.
  - Stop: if reader_precheck and sh4scan have no safe overlap to delegate, choose path (b) with a clear rationale rather than forcing a meaningless import.
  - Claims: C-3410–C-3411
  - Result: EXP-2026-11-09-H48-reader-precheck-sh4scan.md (path a). `reader_precheck.py` imports `sh4scan` and delegates LE halfword edge-scan primitive `_words` → `sh4scan.halfword_array`; `sh4scan`/`reader_precheck` selftests pass (synthetic + real build-A pins when image found). M3.19 reopened by rule 15 note (PR #170) for closure on merge.

- [x] **H37 — 24h senior-engineer review: completed tasks and experiments**
  - Status: done · Owner: task/h37-24h-se-review · Critical: no · Pair: solo
  - Depends: —
  - Goal: audit tasks completed in the 24h window for `Done when` compliance, EXP/TEMPLATE.md quality, claim reproducibility, and retired-lead traps; add follow-up tasks where defects or deepening opportunities exist.
  - Scope: commits `88332de..65e6ae2` on `origin/main` (2026-11-08 24h window); sampled EXPs and TODO task blocks; cheap tool selftests and `claims_check.py`/`todo_check.py`. No vendor-image reruns beyond selftests, no QEMU/Ghidra.
  - Input: `git log --since=24.hours origin/main`, `docs/experiments/EXP-2026-11-08-*` added in range, `docs/experiments/TEMPLATE.md`, `AGENTS.md`, `TODO.md`, `docs/research/claims.md`.
  - Done when: EXP `docs/experiments/EXP-2026-11-09-H37-24h-se-review.md` records the audit (commands, controls, scope, falsifier, observations/interpretation) and TODO contains the follow-up tasks from this pass.
  - Claims: C-3130–C-3139
  - Result: EXP-2026-11-09-H37-24h-se-review.md (80 commits 88332de..65e6ae2 audited; 7 follow-up tasks added H38/H39/M4.35/M5.31/M5.32/M9.28; claims_check OK; sampled selftests OK; no done-task status reversals).

- [x] **H38 — `selftest.py`: discover and run `tools/l3_harness` selftests**
  - Status: done · Owner: task/h38-selftest-l3-harness · Critical: yes · Pair: solo
  - Depends: —
  - Goal: prevent L3 harness regressions from bypassing the main selftest gate (M9.20 noted `tools/selftest.py` does not discover `l3_harness/`).
  - Scope: `tools/selftest.py` discovery/wiring and/or a thin wrapper; run `tools/l3_harness/selftest.py` (and any `l3_harness` tools with `--selftest` that fit the suite contract) as part of `python3 tools/selftest.py`. No behavior changes to harness logic.
  - Input: `tools/selftest.py`, `tools/l3_harness/selftest.py`, `tools/l3_harness/dispatch.py --selftest`, `tools/l3_harness/engine.py --selftest`, `tools/l3_harness/runner.py selftest`, `tools/l3_harness/ghidra/l3_run.py --selftest`; EXP-2026-11-08-M9.20.
  - Done when: `python3 tools/selftest.py` reports the l3_harness checks (or a named aggregate) and exits non-zero on harness selftest failure; `python3 tools/selftest.py --only l3_harness` (or documented selector) works if selectors are supported; SKIP/blocked cases remain honest (e.g. Ghidra/QEMU absent). `tools/README.md` updated if needed.
  - Stop: if `l3_harness` selftests require environment assumptions incompatible with the main suite, integrate them as an explicit sub-suite with clear SKIP reasons and keep the main gate green only when the sub-suite passes or is honestly skipped.
  - Claims: C-3160–C-3169
  - Result: EXP-2026-11-09-H38-selftest-l3-harness.md (`selftest.py` discovers `tools/l3_harness/`+`ghidra/`, reports aggregate `tool:l3_harness` PASS and compatible `tool:l3_harness.*` suites; `--only l3_harness` works; full `selftest.py` 103 suites 81 PASS/0 FAIL/22 SKIP; FAIL propagation verified by control; Ghidra/QEMU absence honest SKIP/BLOCKED inside aggregate, never PASS; README updated; no harness logic changes; `todo_check`/`claims_check` OK with pre-existing warnings only).

- [x] **H39 — `ze0-viewer/harness.py info`: tolerate opaque/unparseable records**
  - Status: done · Owner: task/h39-ze0-viewer-info · Critical: no · Pair: solo
  - Depends: —
  - Goal: make tile inspection usable on factory tiles that contain opaque/bad records (M5.4 noted `harness.py info` crashes with `zlib.error` on `B48R058R`; `harness.py verify` still runs).
  - Scope: `tools/ze0-viewer/harness.py` `cmd_info`/info path only. No parser behavior changes in `tools_ze0` unless required and isolated; prefer catching/reporting bad records with counts and offsets.
  - Input: `tools/ze0-viewer/harness.py`, `tools/ze0-viewer/tools_ze0/` readers, EXP-2026-11-08-M5.4 (Observation 3/7 notes), EXP-2026-11-08-M9.22 (opaque B30R048R context).
  - Done when: `python3 tools/ze0-viewer/harness.py info <tile>` on a tile containing the known opaque/bad-record pattern reports the records as bad/opaque with counts (and does not crash), while `verify` behavior remains unchanged for the checked cases; a synthetic or minimal fixture covers the crash path if practical, otherwise the EXP records the real-tile command/result and SHA-256.
  - Stop: if the crash is inside vendored `tools_ze0` and cannot be fixed without changing pinned vendor behavior, document the limitation, add a targeted wrapper/fallback in `harness.py`, and file a follow-up naming the vendored function.
  - Claims: C-3180–C-3189
  - Result: EXP-2026-11-09-H39-ze0-viewer-info.md (harness.py `--selftest` PASS, synthetic no-vendor fixture: bad zlib record reported as `unreadable/opaque 1` with dir/slot/k locator, no crash; clean synthetic info/verify unchanged; `read_tile`/header/bbox parse failures caught with scan fallback; `cmd_verify`/`tools_ze0` unchanged; real `B48R058R` not rerun here — M9.25 EXP covers).

## M1 — Firmware tooling (archived)

- [x] **M1.18 — Bound `l3_harness` selftest runtime and keep full coverage available**
  - Status: done · Owner: task/m1.18-l3-harness-selftest-runtime · Critical: no · Pair: solo
  - Depends: — (coordinates with H38)
  - Goal: `tools/l3_harness/runner.py --selftest` / full L3 harness checks can dominate agent loops (observed timeout during SE review); make the fast path bounded while preserving a full, honest selftest.
  - Precheck: reproduce baseline runtime: `python3 tools/l3_harness/runner.py --selftest` or the harness aggregate used by H38/selftest.py; record wall time and which cases dominate.
  - Scope: `tools/l3_harness/selftest.py` and/or `runner.py selftest` interface (add `--quick`/`--full` or split slow cases, name chosen form in PR) plus documentation; integrate cleanly with H38/selftest.py selectors. No change to verdict semantics; SKIP/BLOCKED remain honest.
  - Input: `tools/l3_harness/selftest.py`, `runner.py`, `dispatch.py`/`engine.py`/`ghidra/l3_run.py` selftests, H38, `tools/selftest.py`.
  - Done when: the default/quick harness check used by main loops completes within a documented bound and `--full` (or equivalent) still runs the complete suite; `selftest.py` behavior remains correct; EXP records timings and controls (quick pass, full pass, or explicit SKIP reasons).
  - Stop: if PySh4/module-mapping cases cannot be made fast without reducing coverage, keep them in `--full` and document the split; do not remove slow-but-meaningful checks.
  - Claims: C-3390–C-3399
  - Result: EXP-2026-11-09-M1.18-l3-harness-selftest-runtime.md — `--quick` (default) / `--full` on engine, runner, l3_harness/selftest, dispatch, ghidra/l3_run; quick bounded <0.2s each (engine ~0.06s) and skips external Ghidra/QEMU execution honestly (`SKIPPED_IN_QUICK`/`MISSING_*`, never PASS). Full runs complete suite with wall-clock bounds (runner full 45.10s OK; engine full attempts QEMU parity and fails loudly on this host's unverified gdbstub adapter, 60s bound). `tools/selftest.py`, `claims_check.py`, `todo_check.py` pass.

## M3 — Reader contract (archived)

- [x] **M3.21 — Close M3.19: reproduce all `sh4scan` counts on IMG256 including `mask-pair --via-reg`**
  - Status: done · Owner: task/m3.21-close-m3.19-sh4scan-counts · Critical: yes · Pair: solo
  - Depends: M3.19, M3.20
  - Goal: M3.19 is open after M3.20 added register-AND mask handling, but its done-when requires reproducing every published count on IMG256 (including the M3.11 mask hit) and recording the corpus. Verify and close M3.19 or record a precise discrepancy.
  - Precheck: `python3 tools/sh4scan.py --selftest` passes and `--help` shows `mask-pair --via-reg`; `python3 tools/fetch_image.py --image IMG256 -o IMG256.head` can obtain the pinned head (rule 11).
  - Scope: run `sh4scan.py` subcommands on IMG256 build A (`--image-start 0x200200`) for the counts in M3.19 scope: corpus bytes/sections, tags/pattern `8868`, `mask-pair` and `mask-pair --via-reg` for the M3.11 case, stride, anchors. Compare to published counts; do not adjust tool to fit (AGENTS/EXP stop rule).
  - Input: `tools/sh4scan.py`, M3.19 EXP/count list, M3.20 `--via-reg`, IMG256 `92aa525d…`.
  - Done when: an EXP table shows each published count, the command, and reproduced? (yes/no) on IMG256; M3.19 is set `done` with `Result:` if all counts reproduce (with M3.20 variant where applicable), or `blocked` naming the exact differing count/site and `Unblock:`. Any non-reproduced published number is corrected in claims/EXP text, not hidden.
  - Stop: if IMG256 cannot be obtained in the environment, set `blocked` with fetch/provenance issue named (not "no image" as a blanket blocker — use fetch_image path per rule 11).
  - Result: `docs/experiments/EXP-2026-11-09-M3.21-sh4scan-counts-repro.md` (C-3380). All M3.19-scoped published counts reproduced on IMG256 `92aa525d…` incl `mask-pair --via-reg`=1 @ Navi.exe `0x003715c8/ca/cc R3 (+4 B)`, pattern `8868` 23 incl `0x0037c268`, anchors 527/282/245/23559542 B; no published count corrected. M3.19 already `done` (PR #172/H48). `claims_check`/`todo_check`/`sh4scan --selftest` OK.
  - Claims: C-3380–C-3389

## M5 — OSM compiler vertical slice (archived)

- [x] **M5.23 — Confirm road-record country word and provisional class mapping**
  - Status: done · Owner: task/m5.23-roadrec-country-class · Critical: no
  - Depends: M5.4 (done)
  - Goal: M5.4 used a provisional class table and a country word taken from the
    factory context; both are unconfirmed. A wrong country/class field can make
    a structurally valid tile render or route incorrectly.
  - Precheck: decode the country/class bytes of factory road records in
    `B48R058R` (and one other tile) with a control (a record whose class is
    visually obvious in the factory name/geometry).
  - Scope: the road-record fields M5.4 writes from the provisional table; does
    not solve road-class semantics globally (M4.17/M5.3).
  - Done when: the country word and the class field mapping are confirmed on
    factory records with a table in the EXP, and `tilewriter.py` uses the
    confirmed mapping (or keeps a named provisional mapping with the evidence
    gap stated).
  - Stop: if the fields vary by layer/kind in a way one table cannot capture,
    record the cases and scope the writer to the confirmed subset.
  - Result: EXP-2026-11-08-M5.23-roadrec-country-class (C-2660–C-2666).
    Level-1 `0x00fa` country confirmed as header `w[20]` = ISO 3166-1 numeric,
    per record (`w[19]=0`, 45,887 EU records, cross-border variation). Class
    mechanism `(layer, cls_hi=w[p+2]>>12)` confirmed for all 5 `fa_encode.CLASSES`
    `(l1,c1)` buckets; OSM→value mapping kept as **named provisional** (factory
    has unmapped `(layer,cls)` e.g. `(6,7),(6,6),(7,2),(0,10),(0,12)`, M5.3).
    `tilewriter.py` documents confirmed/provisional semantics; `fa_encode`
    level-1 `w[19]` aligned to factory `0`.
  - Claims: C-2660–C-2669

- [x] **M5.31 — `mkcard --reconcile` resize: envelope contract, stale-tail policy, fresh-build contrast**
  - Status: done · Owner: task/m5.31-mkcard-reconcile-resize · Critical: no · Pair: required
  - Depends: M5.20
  - Result: EXP-2026-11-09-M5.31-mkcard-reconcile-resize. `mkcard --reconcile` names actual DRSTR index/value bytes as `drstr:index` with image offsets (eu-grow: 2 ranges, `drstr_other` absent) and classifies diff ranges without weakening `outside_count==0`. Stale-tail default zero-fill; opt-in `--preserve-stale-tail` preserves factory slack only in existing-chain clusters (newly allocated clusters zero-filled), tested one-variable in R8 with invariants preserved. EU2011 (`105e2032…`) uncapped contrast, one variable: eu-same reconcile 1 range / fresh 24,173,274 ranges (~5.17 GB); eu-grow reconcile 246 ranges (dir/file/drstr:index) outside 0 cardcheck PASS / fresh 24,173,273 ranges. `mkcard`/`imgpatch` selftests + claims/todo OK.
  - Claims: C-3170–C-3175

