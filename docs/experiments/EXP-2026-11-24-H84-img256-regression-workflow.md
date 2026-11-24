# EXP-2026-11-24-H84-img256-regression-workflow

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** no vendor sample committed; the pinned head is `IMG256` = first
  268435456 bytes of EU2011, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (quoted from `python3 tools/fetch_image.py --list | grep '^IMG256'`).
- **Tools:** `python3 3.11`, `PyYAML 6.0.3`, `bash`, repo tools
  `tools/fetch_image.py`, `tools/realcheck.py`, `tools/selftest.py`,
  `tools/board.py`. No recompression claim, so no `zlibinfo.py` stamp is needed.
- **Claims:** C-4070–C-4079
- **Supersedes:** none
- **Superseded by:** none

## Question

Does a new manual/weekly workflow run `tools/realcheck.py IMG256 --require-image`
against a SHA-256-pinned 256 MiB firmware head, publish an honest PASS/FAIL per
check with an artifact and job summary, and state `SKIP (no image on this
runner)` (neither green-as-passed nor red) when the head is absent — while never
triggering on `pull_request`/`push` and leaving `tools/selftest.py` unchanged?

## Hypothesis

A single new workflow file with only `workflow_dispatch` and `schedule` triggers
satisfies all five Done-when clauses. **Falsifier:** any of — (a) the workflow
lists `pull_request`/`push` under `on:`; (b) a cache miss exits red or prints a
bare success instead of the explicit `SKIP (no image)` summary; (c) the
`--require-image` realcheck command or the pinned digest is absent/mismatched;
(d) `tools/selftest.py` changes vs baseline; (e) any mutation from the negative
control is NOT caught by its grep; (f) a vendor blob is committed.

## Inputs

| Item | Value |
| --- | --- |
| Pinned head | `IMG256` = EU2011 first 268435456 bytes |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Pin source | `python3 tools/fetch_image.py --list \| grep '^IMG256'` |
| Repo tools | `tools/realcheck.py`, `tools/fetch_image.py`, `tools/selftest.py` |
| New artifact | `.github/workflows/firmware-regression.yml`, `.github/workflows/README.md` |

## Method

1. **Sample and hash.** No vendor bytes in the repo. The head is resolved at
   run time from a SHA-256-keyed `actions/cache` or a rule-11 fetch
   (`tools/fetch_image.py --image IMG256`, 256 MiB only), verified by
   `tools/fetch_image.py --verify "$path" --image IMG256`. The pin above is
   quoted from `fetch_image.py --list`; it is never written as a blob.

2. **Commands.** Runnable as written (from the worktree root):
   ```bash
   python3 tools/fetch_image.py --list | grep '^IMG256'
   python3 tools/realcheck.py IMG256; echo $?
   python3 tools/realcheck.py IMG256 --require-image; echo $?
   grep -cE '^  (pull_request|push):' .github/workflows/firmware-regression.yml
   grep -cE '^  (workflow_dispatch|schedule):' .github/workflows/firmware-regression.yml
   grep -c 'realcheck.py IMG256 --require-image' .github/workflows/firmware-regression.yml
   grep -c '92aa525d' .github/workflows/firmware-regression.yml
   grep -c 'SKIP (no image' .github/workflows/firmware-regression.yml
   python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/firmware-regression.yml')); print(list(d.get('on', d.get(True)).keys()))"
   python3 tools/selftest.py
   ```

3. **Controls.** *Positive:* the workflow file exists, declares exactly
   `workflow_dispatch` + `schedule`, contains the literal
   `realcheck.py IMG256 --require-image` command, the pinned digest quoted from
   `fetch_image.py --list`, and `SKIP (no image)`; the README documents the
   policy. *Negative (mutations on a COPY in scratch, never the worktree):*
   (1) add `pull_request:` under `on:` → PR-trigger grep > 0; (2) delete the
   `schedule:` block → dispatch/schedule count drops to 1; (3) drop
   `--require-image` → command grep 0; (4) alter the digest → digest grep 0.
   A negative claim without this positive control is not a result.

4. **Scope.** In scope: one new workflow file and `.github/workflows/README.md`.
   Corpus: the five existing `.github/workflows/*.yml` files (the precheck
   `grep -lE 'workflow_dispatch|schedule' .github/workflows/*.yml | wc -l`
   prints **1** today — only `main-watch.yml`, so H84's stale premise of `0` is
   not restated) plus the new file. Inputs read-only: `tools/realcheck.py`
   exit codes, `tools/fetch_image.py` (IMG256 pin, `--image`, `--verify`),
   `tools/selftest.py`. Excluded: no 7.4 GB image, no card tree, no
   `l3check --card` gate (M9.12/H43), no edit to any existing workflow, no
   gate/tool/selftest change.

5. **Falsifier.** Cache-miss red or silent green; any PR/push trigger; missing
   realcheck command or mismatched digest; changed selftest; any mutation not
   caught; any committed vendor blob.

## Observations

Raw command outputs (numbers quoted from the printing commands):

- `python3 tools/fetch_image.py --list | grep '^IMG256'` →
  `IMG256 268435456 92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9 = EU2011 --part 256M`.
- `python3 tools/realcheck.py IMG256; echo $?` → eight `SKIP … no image` lines,
  `realcheck: 0 PASS, 0 FAIL, 8 SKIP`, rc **2**.
- `python3 tools/realcheck.py IMG256 --require-image; echo $?` → eight
  `FAIL … no image` lines, `realcheck: 0 PASS, 8 FAIL, 0 SKIP`, rc **1**.
- Unmutated artifact greps: PR/push triggers **0**; dispatch+schedule **2**;
  `realcheck.py IMG256 --require-image` **3**; digest `92aa525d` **1**;
  `SKIP (no image` **2**; `--verify … --image IMG256` **1**.
- PyYAML parse → `triggers: ['schedule', 'workflow_dispatch']`,
  `has pull_request: False has push: False`, `run_img256 default: False`,
  `timeout-minutes: 20`.
- Negative mutations on scratch copies: add `pull_request:` → PR/push count
  **1** (caught); delete `schedule:` → dispatch/schedule count **1** (caught);
  drop `--require-image` → command count **0** (caught); alter digest → digest
  count **0** (caught).
- SKIP summary simulation (no-image branch, local shell) emitted
  `### SKIP (no image on this runner)` once and exited **0**.
- `python3 tools/realcheck.py --selftest` → `16 checks OK (synthetic CE ROM,
  no vendor data)`; `python3 tools/fetch_image.py --selftest` → `failures: 0`.
- `python3 tools/selftest.py` → (baseline result quoted in the final commit;
  no tool changed, so no delta expected).

## Interpretation

- **FACT:** the workflow declares only `workflow_dispatch` and `schedule`;
  PyYAML shows no `pull_request`/`push` key. The pinned digest matches
  `fetch_image.py --list` exactly. The literal `--require-image` command runs
  the eight pinned checks.
- **FACT:** on this host (no image) the two local controls reproduce realcheck's
  0 PASS/0 FAIL/8 SKIP (rc 2) and 0 PASS/8 FAIL/0 SKIP (rc 1) contracts verbatim.
- **OBSERVED:** the SKIP branch writes an explicit label and exits 0 — the
  GitHub Actions analogue of gate.py's SKIP (exit 0 with a SKIP label, no PASS
  claimed). A genuine check FAIL propagates rc 1 (red).
- **HYPOTHESIS:** on a runner with the cached/fetched verified head the
  realcheck step reports PASS/FAIL per check and uploads the artifact; with no
  head the job is honest-SKIP. Not executable here (no image, no CI runner),
  so this remains a documented contract, not a live acceptance.
- **UNKNOWN:** the scheduled job's network reachability to `files.viaaq.eu`
  from the chosen runner; the workflow degrades to SKIP when it is absent.

## Conclusion

Added `.github/workflows/firmware-regression.yml` (manual/weekly only, never
PR/push) and documented the policy, cost and SKIP≠PASS semantics in
`.github/workflows/README.md`; C-4070–C-4079 record the contract. The workflow
resolves the SHA-256-pinned 256 MiB head, runs `realcheck.py IMG256
--require-image` with an artifact and per-check summary, and states
`SKIP (no image)` on a cache miss. `tools/selftest.py` is unchanged. This is a
firmware-head regression, not rule-13 card acceptance.

## Corrections after navigator review

- MUST-FIX 1: the resolved verified head path is now captured in
  `steps.verify.outputs.path` and symlinked to `IMG256`, so the literal
  `realcheck.py IMG256 --require-image` runs against the real file instead of a
  missing path (which would be a permanent false-red). Documented above.
- MUST-FIX 2: `run_img256` now gates only the optional L3 corpus step; a
  `schedule` event has no dispatch inputs, so the core realcheck runs on both
  triggers regardless — the weekly regression cannot become a no-op.
- SHOULD-FIX 4: verify now pins `--image IMG256` explicitly.
- SHOULD-FIX 3: the EXP/README state plainly that SKIP means exit 0 with a SKIP
  label and no PASS claimed; a real FAIL still propagates rc 1.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fetch_image.py --list | grep '^IMG256'
python3 tools/realcheck.py IMG256; echo $?              # expected: 2
python3 tools/realcheck.py IMG256 --require-image; echo $?  # expected: 1
grep -cE '^  (pull_request|push):' .github/workflows/firmware-regression.yml   # 0
grep -cE '^  (workflow_dispatch|schedule):' .github/workflows/firmware-regression.yml  # 2
python3 tools/selftest.py
```

## Follow-ups

- [ ] TL runs `workflow_dispatch` on a runner with the head cached / network to
      `files.viaaq.eu` and confirms a live PASS/FAIL summary + artifact.
- [ ] If the approved runner cannot fetch within 20 min, keep the dispatch
      skeleton and record the fetch gap (H84 Stop); do not vendor the head.
