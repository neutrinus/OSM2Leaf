# TODO history — 2026-11-23

Done tasks moved from `TODO.md` on 2026-11-23 with `tools/board.py archive`.

- [x] **H105 — H40's fixture has no negative control: a tree that passes but cannot fail proves nothing**
  - Status: done · Owner: task/h105-cardcheck-negative-control · Critical: yes · Pair: required
  - Depends: H103 (the builder it breaks); H40's Done-when calls it
  - Goal: retro 2026-11-18 action 3's Done-when is "`l1l2-fixtures.yml` runs `cardcheck` on a generated tree **and fails on a broken one**". H103 gives the passing tree; the broken one is the control that makes the row a test. Without it, a check that silently degraded to `return PASS` passes both the tree and CI, and H40 closes on a no-op — exactly the B2/N1 defect class M5.34's reviewer found (out-only file, section-2 flip).
  - Precheck: `grep -c 'break\|corrupt\|negative' tools/one_tile_pipeline.py` counts only the reviewer-added `out == input` and section-2 checks — there is no builder that emits a *deliberately* broken card; H40's block has no negative clause today.
  - Scope: a `--break <kind>` option on H103's builder (kinds named in the PR: `mmain-missing-tile-level`, `drstr-size-mismatch`, `tile-level-not-in-mmain`, `fat-cluster-out-of-range`, `header-magic`) plus the H40 registry row that asserts `rc=1` and that the JSON names the *same* check id the good tree passed. Exclusion: no new validator rule (the break must trip an existing check — a new check is H103's Step), no vendor bytes.
  - Input: H103's builder, `tools/cardcheck.py` check ids and exit codes, `tools/l1l2_fixtures.py` (where the pair goes), M5.33's recorded rc=1 detail (section 2 levels 2/4/5, section 4 level 1 not in `MMAIN`) as the natural first break kind.
  - Hints: the control is `good rc=0 → break rc=1 → same build without the break rc=0` in one run, so a flaky temp dir cannot fake it. A break kind that no check notices is a finding: record it as a missing check (a new block), do not delete the kind.
  - Done when: `python3 tools/cardcheck.py --generate-fixture DIR --break tile-level-not-in-mmain --json …` exits 1 and the JSON's failing id equals the id the unbroken tree passed; `--selftest` runs every break kind and asserts rc=1 for each; `python3 tools/l1l2_fixtures.py --selftest` covers the pair.
  - Stop: if a break kind trips several checks at once and cannot be narrowed, keep it but assert only "the target id is among the FAILs" and say so in the row's reason.
  - Falsifier: the good tree passes and every `--break` kind also exits 0 (the checker never distinguishes them).
  - Claims: C-4360–C-4369
  - Result: EXP-2026-11-21-H105-cardcheck-negative-control; C-4360–C-4369. --break (5 kinds) on H103's builder: `--generate-fixture DIR --break tile-level-not-in-mmain --json J` exits 1 with FAIL id `mmain`, the id the unbroken tree passes (good rc=0, 6 PASS/2 SKIP); all five kinds rc=1 with their target id among the FAILs (`mmain`,`mmain`,`drstr`,`headers`,`fat`), each an existing rule (no new validator rule). The `fat` kind needs clusters, so `--generate-fixture-image` adds a vendor-free sparse ~100 MiB FAT32 image the checker accepts 8/8 (mbr/fat PASS, not SKIP), byte-identical over two builds; a `--root` tree run exits 2 (lane limit). `cardcheck --selftest` runs every kind (30 ok, 0 fail); `l1l2_fixtures` `l1.synthetic.cardcheck` runs the good+break pair in one row (PASS, coverage_gaps []), `--selftest` OK (32 checks). Gate 4/4 PASS (run with TMPDIR on the home disk: `/tmp` was 97% full and `mkcard --selftest` hit ENOSPC there; `mkcard` passes with a roomy TMPDIR). H40 (CI row) and H104 (baseline) stay their blocks.

- [x] **H121 — A PR must not delete claim rows or task blocks it does not own (main lost 199 claim rows and 7 tasks in PR #340)**
  - Status: done · Owner: task/h121-board-mergebase-check · Critical: yes · Pair: required
  - Depends: —
  - Goal: commit `6ca7bc3` of PR #340 (M9.55, merged 2026-11-20 22:20 UTC) replaced the tail of `TODO.md` (from the M9 section on, 787 lines) and of `docs/research/claims.md` (324 lines, 28 sections) with an older copy after a conflict. Every gate passed: `todo_check` and `claims_check` judge the file they are given and cannot see what is gone. Main ran 100 minutes without M9.56–M9.62, with nine closed tasks open again and without the claims of 28 tasks, and three later PRs merged on top. The loss was restored by hand (this PR), found only because a 3-way merge deleted another branch's rows.
  - Precheck: `git diff --numstat 4900961 6ca7bc3 -- TODO.md docs/research/claims.md` prints `1 787` and `11 324`.
  - Scope: one check in `tools/gate.py` and CI (`quality`): against the merge base with `origin/main`, list claim IDs and task IDs that exist in the base and not in the branch; fail unless each is named in the PR's own task block (archive move: the ID must then exist in `docs/research/todo-history-*.md`), or is a `RESERVED` row. No change to the two checkers' other rules.
  - Input: `tools/claims_check.py`, `tools/todo_check.py`, `tools/gate.py`, `.github/workflows/`.
    Reuse `tools/board.py` (`lost_ids`, `lost --base`; H123) for the ID diff instead of a second parser.
  - Done when: on a checkout of `6ca7bc3` the check exits 1 and names the lost task IDs and the count of lost claim rows; on `main` it exits 0; `--selftest` covers a deleted row, a deleted task block, an archived task and a dropped `RESERVED` row.
  - Stop: if the merge base cannot be found in CI's shallow clone, fetch `origin/main` with depth 200 in the workflow and record the time it adds.
  - Falsifier: a legitimate PR of the last 50 merged that the check would have failed (then widen the exemption and say which).
  - Claims: C-6520–C-6529
  - Result: EXP-2026-11-21-H121-board-mergebase-check; C-6520–C-6529. `board.py check 6ca7bc3` exits 1 naming 42 lost tasks and 199 lost claim rows; `check origin/main` and `check HEAD` exit 0; `board.py --selftest` OK (74 checks) covers a deleted row, a deleted task block, an archived task, a dropped RESERVED row and the round-1 whole-ID collision (M9.56 does not exempt a lost M9.5); `gate.py --selftest` OK (15 checks); `gate: 5 pass, 0 fail, 0 skip` with `board_check PASS` and `fn_audit PASS` on the tree rebased onto `01a67a6e` (re-frozen fn_audit snapshots from `67a12666` in the base)
  - Note: The main check reads `board.py check <ref>`: the branch was rebased onto `01a67a6e` (round 3, after M1.43/M4.58) before the final run, so the final bases are `HEAD vs 01a67a6ea6b3` (exit 0), `origin/main vs 2c82b9ce2683` (exit 0), `6ca7bc3 vs 49009617d2bc` (exit 1, 42 tasks / 199 claim rows). An unpinned base in a quote is stale by construction once main moves; pin both sides (`check 01a67a6e --base 2c82b9ce`) or cite what the command prints on that tree.

- [x] **H122 — `l3_harness/corpus.py --selftest` fails 4 `hdd_info` checks on main and the gate skips the suite**
  - Status: done · Owner: task/h122-h122-corpus-selftest · Critical: no · Pair: solo
  - Depends: —
  - Goal: `python3 tools/l3_harness/corpus.py --selftest` ends `FAILED (4/14 checks)` on `main` (2026-11-20, also before PR #340): the factory `HDD_INFO.TXT` fixture is `REJECT` where the manifest expects `ACCEPT`, because `hddinfo.classify(...)["accepted"]` is false when the check-2 bounds are unknown (`verdict 'ACCEPT (check1); check2 BOUNDS_UNKNOWN'`). `python3 tools/selftest.py --only l3_harness.corpus` prints `SKIP no --selftest`, so `gate.py` never ran it. Found during M9.10 (C-2149).
  - Precheck: both commands above print what the Goal quotes.
  - Scope: `tools/l3_harness/corpus.py` (`verdict_hdd_info`: decide from `no_proven_failure` or pass declared bounds, whichever matches the M2.15 model; say which in the EXP), `tools/selftest.py` (the suite must be discovered: its `--help` has to declare `--selftest`, or the discovery rule changes). No change to `hddinfo.py`'s model.
  - Input: `tools/hddinfo.py` (`classify`), `tools/l3_harness/corpus.py`, `tools/selftest.py` (`exposes_selftest`), H120 (same class of defect).
  - Done when: `corpus.py --selftest` passes 14/14, `selftest.py --only l3_harness.corpus` runs it (PASS, not SKIP), and a deliberately broken fixture makes `gate.py` fail.
  - Stop: if the M2.15 model says the factory file must not be `ACCEPT` without bounds, change the manifest's expectation instead and record why.
  - Falsifier: another `l3_harness/*.py` suite that `selftest.py` reports as `SKIP no --selftest` while its own `--selftest` exits non-zero.
  - Claims: C-6530–C-6539
  - Result: EXP-2026-11-21-H122-corpus-selftest (C-6530–C-6532): corpus.py --selftest OK (14/14), selftest.py --only l3_harness.corpus PASS, gate.py 4 pass/0 fail/0 skip, corrupted fixture -> check rc=1

- [x] **H127 — A red gate log names no claims_check row: the 5 red `main` runs print 2 gate lines and 40 NONRUN lines, never the failing rule**
  - Status: done · Owner: task/h127-h127-gate-log-failing-row · Critical: no · Pair: required
  - Depends: — (serves H117's diagnosis: `main_watch` can name the SHA and the step, not the rule)
  - Goal: the five red `CI quality gate` runs on `main` since 2026-11-20 (`8e0f913c90`, `28927eb43d`, `13731fe9cf`, `c4b5a90279`, `6834e4b4eb`) all failed on `quality :: Standing gate (tools/gate.py)`, and every red log's `--- claims_check output (tail) ---` section holds only `NONRUN …`/`NOEXP …` warning rows — the actual failing line (`MISSING C-2141 archive/us256.img` for the first four; a `count-check`/evidence line for the fifth) is printed above the last 40 lines and cut off. `tools/gate.py` prints `"\n".join(lines[-40:])` for every non-selftest gate, so a claims_check output of ~500 lines hides its verdict. The weekly/manual README already promises "name the failing row" and cannot: a reader of a red run cannot tell which rule failed without re-running the tool at that SHA.
  - Precheck: `gh run view 44874389818 --log-failed | grep -aE 'claims_check +FAIL|NONRUN|MISSING'` prints the `claims_check FAIL` line plus ~40 `NONRUN` rows and no `MISSING`; `grep -n 'lines\[-40:\]' tools/gate.py` prints the single tail slice used for `claims_check`, `todo_check` and `fn_audit`.
  - Scope: `tools/gate.py` only — per-gate tail filtering that keeps the lines a red run needs: for `claims_check`, the summary lines (`genuine missing evidence paths`, `MISSING …`, `duplicate claim IDs`, `unregistered proposed claims`, `count mismatches`, the `claims_check: FAILED` line) and for `todo_check` the `ERROR` lines and the `todo_check: FAILED` line, each capped at a per-kind limit instead of a blind 40-line slice. Mirror the existing `selftest` special case (`if r["gate"] == "selftest": … shown[-120:]`) with a `_FAIL_HINTS` table; keep the full output available via `--json`/raw. Also print each gate's measured wall time when it FAILs so a slow failure (H84's manual job) is visible. Exclusion: no change to what any gate asserts, no exit-code change.
  - Input: `tools/gate.py` (`_print_table` / the FAIL tail loop, `SKIP_MARKERS`, the `selftest` special case), `.github/workflows/ci.yml` and `README.md` (the `claims_check FAIL` exit 1 policy), the five red run ids above, H117's EXP (`salient_lines` uses the same `STEP_HINTS` idea).
  - Hints: the failure text already carries the rule names (`genuine missing evidence paths: 4`, `MISSING C-2141 …`), so the fix is selection, not new wording. Reuse `main_watch.py`'s `STEP_HINTS` vocabulary rather than a second list. A gate whose output has no hint line must still print its last 40 lines, so an unknown failure is not hidden.
  - Done when: `python3 tools/gate.py` with a temp `docs/research/claims.md` whose one row cites an absent path prints, under `--- claims_check output (tail) ---`, a `MISSING` line naming the claim and the path, before the 40-line cap; with a temp `TODO.md` whose task loses `Scope` the `todo_check` tail names the `ERROR` line; `python3 tools/gate.py --selftest` (or the tool's own selftest) covers both; on `main` the gate stays 4 pass / 0 fail / 0 skip; a real red run after the change (or `--replay` of run ids into the log formatter) names the rule.
  - Stop: if the CI log format cannot be replayed offline, test the formatter directly (`_print_table`/the tail helper) on saved outputs and record that the end-to-end assertion is manual in the EXP.
  - Falsifier: a red claims_check run whose gate log contains no line naming the failing claim/path/rule after this task.
  - Claims: C-6680–C-6689
  - Result: EXP-2026-11-21-H127-h127-gate-log-failing-row (C-6680): tools/gate.py FAIL tails now select hint lines per gate (FAIL_HINTS: claims_check keeps MISSING/genuine missing/count mismatches/…/FAILED; todo_check keeps ERROR/FAILED; fn_audit keeps GAP/UNMAPPED/FAILED) capped at 40 with an elision marker, plus 40 trailing non-hint lines and a per-gate wall-time line; gates with no hint table or no matching hint keep the blind 40-line tail, so unknown failures are not hidden. gate.py --selftest OK (16 checks); gate.py 4 pass/0 fail/0 skip. Verified: a synthetic MISSING row survives the cap (the earlier reproduction printed it first), and a missing Claims field surfaces its ERROR line.

- [x] **H128 — `todo_check --strict` has no ledger of its own debt: 8 ERROR held by open PRs, and no baseline says whether the count grew**
  - Status: done · Owner: task/h128-h128-todo-strict-debt · Critical: no · Pair: required
  - Depends: — (H53 lowered its own Done-when to "no ERROR for tasks this cycle can own"; this task makes the remainder measurable)
  - Goal: the QA prompt says report the `--strict` count and "do not treat it as a new regression until H53 cleans it" — but nothing records what the count was, so each pass re-derives "8 ERROR / is it new?" by memory. At `b67d1519` `python3 tools/todo_check.py --strict` exits 1 with **8 ERROR** over **4** tasks (`M1.38`, `M3.13`, `M3.29`, `M8.C`; two of them also `WARN … references blocked task`) and **181 WARN**. H53's Result recorded 17 ERROR over 7 tasks at `ea15563` and said they "clear when those land `done`" — 3 of those 7 are still open (`M3.13 #351`, `M3.29 #341`, `M8.C #355`), so the debt is a set of PRs, not a number to eyeball. A baseline keyed by task ID turns "it grew" into a command.
  - Precheck: `python3 tools/todo_check.py --strict >/tmp/opencode/tc.txt 2>&1; echo $?` prints `1`; `grep -cE '^  ERROR' /tmp/opencode/tc.txt` prints `8`; `grep -E '^  ERROR' /tmp/opencode/tc.txt | sed -E 's/.*TODO.md:[0-9]+ ([A-Z0-9.]+):.*/\1/' | sort -u` prints the four IDs above; `python3 tools/todo_check.py; echo $?` prints `0` (default stays green).
  - Scope: `tools/todo_check.py` only — `--baseline PATH` / `--update-baseline PATH`: a committed `tools/fixtures/todo_strict_baseline.json` records each `(task ID, field)` that ERRORs at a pinned revision, and `--strict --baseline` exits 1 on **any** ERROR whose task ID is not in the baseline (a new one) and prints, but does not fail, a baseline entry that has cleared (that is the H53 progress); snapshot the IDs with `git rev-parse HEAD` in the file header. Also make the `--strict` summary print `ERROR n over m tasks (baseline k, new N)` so the log carries the number. Exclusion: do not suppress a WARN, do not relax the firmware four-field rule, no edit to any open task's block (H53's Stop: the PR-held tasks are not ours to edit).
  - Input: `tools/todo_check.py` (`REQUIRED`/`strict_firmware`, `_parse_depends`, the `--strict` path), H53's Result (`17 ERROR / 7 tasks` at `ea15563`, EXP-2026-11-20-H53-strict-honest), H120 (the same "a check must know what it measured" class), the current four task IDs.
  - Hints: key by `(task ID, missing field)`, never by line number (H71/H80). The baseline is a *debt ledger*, not a waiver: a new task with a missing `Scope` must fail on the first PR that adds it, or the rule is dead. `--update-baseline` must print the exact `+`/`-` rows and require the file to be staged, like H104's `cardcheck` baseline.
  - Done when: `python3 tools/todo_check.py --strict --baseline tools/fixtures/todo_strict_baseline.json` exits 0 on `main` (the 8 are all baselined) and prints `ERROR 8 over 4 tasks (baseline 8, new 0)`; a temp `TODO.md` with one extra firmware task missing `Stop` exits 1 and names it; a temp `TODO.md` with one baseline task completed/archived prints `cleared: M3.13` and still exits 0; `python3 tools/selftest.py --only todo_check` PASS; `python3 tools/todo_check.py` (default) still exits 0.
  - Stop: if the strict ERROR set changes with every PR-held merge (it will, as #351/#341/#355 land), the baseline is still correct — those merges clear entries, and the task says so; do not pin the count as a constant in prose, pin the IDs.
  - Falsifier: after this task a new firmware task with a missing `Precheck`/`Scope`/`Stop` still exits 0 under `--strict --baseline`.
  - Claims: C-6700–C-6709
  - Result: EXP-2026-11-21-H128-h128-todo-strict-debt (C-6700): tools/todo_check.py gains --baseline/--update-baseline; committed tools/fixtures/todo_strict_baseline.json keys 8 ERRORs over 4 tasks (M1.38, M3.13, M3.29, M8.C) by (task ID, missing field). --strict --baseline exits 0 on main (8 over 4, baseline 8, new 0), a new firmware task missing Stop exits 1 (NEW M9.99|Stop), a cleared task prints cleared: M3.13 and stays 0; structural errors (no key) always fail. selftest 31 checks, default mode still 0. No WARN suppressed, firmware rule unchanged, no open task edited.

- [x] **H61 — `claims_check`: every cited EXP record must exist on `main`**
  - Status: done · Owner: task/h61-claims-exp-exists · Critical: no · Pair: solo
  - Depends: — (`tools/claims_check.py` is on `main`); coordinates H58 (same tool, evidence *command*; this one checks the evidence *name*)
  - Goal: `claims_check.py` verifies IDs and annotations but never resolves the EXP record a row names, so a typo'd or absent record looks registered. Today `C-1900–C-1916` cite `EXP-2026-11-08-M4.8b-poi-refs` while the repo stores `EXP-2026-11-08-M4.8b-poi-refs.tsv` (7 rows), and `C-3033` cites `EXP-…-variants.tsv` (a `.tsv`, not a record); `C-3170–C-3175` cite the `.md` suffix in prose. A row must name a file that exists, or say why it has no record.
  - Precheck: `python3 -c "import re,glob,os;m={os.path.basename(p)[:-3] for p in glob.glob('docs/experiments/EXP-*.md')};n=[l.split('|')[1].strip() for l in open('docs/research/claims.md') if l.startswith('| C-') and any(not any(p==s or s.startswith(p+'-') for s in m) for p in [x.rstrip('.,;').removesuffix('.md') for x in re.findall(r'EXP-\d{4}-\d{2}-\d{2}-[A-Za-z0-9.\-]+',l)])];print(len(n),n[:4])"` prints `8 ['C-1900', 'C-1901', 'C-1902', 'C-1903']` — the `poi-refs` rows name a `.tsv`, `C-3033` names a `.tsv` with its suffix. (A loose match that also accepts `EXP-…-<slug>.<ext>` reports 0 and hides both; the rule below must therefore require a `.md` record or an explicit `companion:` in the row.)
  - Scope: `tools/claims_check.py` only: resolve each `EXP-YYYY-MM-DD-<TASK>-<slug>` token against `docs/experiments/` by exact file name, `.md` suffix, or `<name>.<ext>` (a `.tsv`/`.json` companion next to an `EXP-…` record is allowed); report one line per unresolved row and a total; land it as a warning by default and an error under H58's `--strict`. Do not touch the duplicate/unregistered/annotation checks or H58's command-span parser.
  - Input: `docs/research/claims.md` (all rows), `docs/experiments/` listing, `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`), EXP-2026-11-08-M4.8b-poi-refs.tsv (the `.tsv`-only record the rule must allow).
  - Hints: keep the stem match (`-2`/`-3` suffixes count as the same task), resolve relative to `REPO` like `fn_audit` does, and do not grep EXP *contents* — a missing file is the defect, a missing section is a reviewer's job. Reuse H58's `--strict` rather than a second flag.
  - Done when: `python3 tools/claims_check.py --selftest` covers a row naming a missing EXP (fails), one naming a `.md` record (passes), one naming a `.tsv` next to its stem (passes) and a `-2` suffix (passes); default `claims_check.py` still exits 0 on the current ledger and prints the unresolved count; `--strict` (once H58 lands it) exits 1 and names at least `C-1900` and `C-3033`; `selftest.py` passes.
  - Stop: if H58's `--strict` has not merged, ship the warning mode plus `--selftest` and record in the EXP which rule H58 must pick up; do not fork a second ledger checker.
  - Claims: C-3810–C-3819
  - Result: EXP-2026-11-19-H61-claims-exp-exists — `unresolved_exp_names()` names 8 rows at `fa7c8af` (C-1900–C-1906 `no-record`: only `poi-refs.tsv` exists; C-3033 `companion-unmarked`), not C-3170–C-3175; default and `--strict` (the gate) stay exit 0 and print the count, H58's `--strict-evidence` exits 1 naming C-1900 and C-3033 (H58's Stop kept `--strict` warning-only); `--selftest` 50 checks (C-3810–C-3815).

- [x] **H94 — H90's EXP sat "done" with hand-typed counts and a broken commands section**
  - Status: done · Owner: task/h94-h94-exp-counts-commands · Critical: no · Pair: required
  - Depends: H90 (the EXP it repairs is on `main`; H93 owns the navigator section only)
  - Goal: make H90's EXP re-runnable as written — every count quoted from a command that prints it, the clone recipe one copy-pasteable block that still demonstrates the defect, and the failed-run count consistent with C-4130.
  - Note (SE 2026-11-17): the SE re-ran H90's Done-when (b)-(e) and all pass, but three EXP defects survived the pair: the Record `809 commits, pack 3.2 MiB` and `Tools: git 2.5x, python3 3.15` are typed, not from a command (AGENTS "every number is quoted"); the Method command block lists `git clone … /tmp/x && cd /tmp/x` then a second `git fetch --unshallow` line that would run in the wrong cwd; and "the five `main` pushes whose run failed" contradicts the nine `COUNT` lines and the twelve red pushes the same EXP states. The recipe also now fails as written: on today's `main` a depth-1 clone prints `count check: skipped`, not `9` (C-4131 covers this, the Reproduction block does not).
  - Note (H93, 2026-11-20): the Reproduction block is already done by H93 (#377). It is a depth-1 fetch of `3d79bcc` itself and prints 9 mismatches/exit 1 shallow and 0/exit 0 after `--unshallow`. The Reproduction clause is dropped from this task's Scope and Falsifier; the Precheck's clone line describes the state before H93.
  - Precheck: `grep -nE '809 commits|git 2\\.5x|python3 3\\.15|five .main. pushes' docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` prints the typed lines; `rm -rf /tmp/x && git clone --depth 1 file://$PWD /tmp/x && (cd /tmp/x && python3 tools/claims_check.py --strict --count-check | tail -1)` prints `claims_check: OK`, not the `9` the Reproduction says.
  - Scope: `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` only: quote `git rev-list --count 3d79bcc` and `git count-objects -vH | grep size-pack`; state the interpreter `python3 -V` prints and `git --version`; collapse the two-line clone recipe into one `( cd /tmp/opencode/x && … )` subshell; change "five" to the actual failed-run count the `gh run list` prints. No claim rows; H93 owns the navigator section.
  - Input: the H90 EXP, `docs/experiments/TEMPLATE.md`, C-4131/C-4135, `git rev-list --count`, `git count-objects -vH`.
  - Hints: the `12` in C-4130/C-4131 and the H90 Goal is correct (`gh run list` shows twelve `failure` rows before the first post-fix `success`); the "five" is the only run-count defect. Do not re-pin C-4135's `809`/`3.2 MiB` to `main`'s today value — the claim names `3d79bcc`, so quote the number at that commit and say so.
  - Done when: `grep -cE '809 commits|5x|3\\.15|five .main. pushes'` on the EXP is 0 or each hit cites the command that printed it; the clone recipe is one copy-pasteable block and H90's Done-when (b)-(d) still pass as run in H94's EXP. `python3 tools/claims_check.py --strict --count-check` and `todo_check.py` OK.
  - Stop: if the count really cannot be shown from a command at `3d79bcc`, delete the number and point at C-4135 instead of retyping it.
  - Falsifier: the typed `809 commits`/`3.15` strings remain.
  - Claims: C-4200–C-4209
  - Result: EXP-2026-11-21-H94-exp-counts-commands (C-4200): H90's EXP numbers now cite commands (git rev-list --count=108, git count-objects=19.74 MiB, git --version=2.56.0, python3 -V=3.15.0; 809/2.5x/3.15 labelled H90's, pinned by C-4135), clone recipe collapsed to one ( cd "$X" && ... ) block, failed-run count now 12 (1889340..2b3d1b4) matching C-4130; H90 Done-when (b)-(d) still pass (claims_check --selftest OK 51, gate.py 4 pass/0 fail/0 skip, --strict --count-check OK, todo_check OK)

- [x] **M1.19 — Wire the kernel decompressor into `cerom.py`, `rommap.py` and `va_class.py`**
  - Status: done · Owner: task/m1.19-kernel-decomp-wiring · Critical: yes
  - Result: EXP-2026-11-19-M1.19-kernel-decomp-wiring; C-3500–C-3506. `cerom.py --image-start 0x200200 IMG256 decompress --check` → `245 OK, 0 UNSUPPORTED, 0 FAIL` with `r0 == comphdr uncompressed_len` for all 245 (EU2011, 1,674,478 B) and 249/249 on US256 (US2011, 1,684,059 B); `nk_decomp` gained a cached library interface (`section_init`/`section_bytes`/`load_image`, cache `$OSM2LEAF_DECOMP_CACHE` or `archive/work/decomp/`); `rommap.py --init-from-image` maps decoded INIT + zero BSS with IAT bound and no guard; `runner.py run cmp_ind_reader` (EU2011) and `cmp_ind_reader_us2011` PASS with `sec1_table.source: image` (no declared values; mask words equal `2^n-1`; counters equal the declared run, zero-sec1 control FAILs); probes `mmain_reader` → `BLOCKED STUB COREDLL.dll!wcstombs`, `drstr-sub_00419350` → `BLOCKED STUB OSMDLL.dll!OSM_Malloc` (same under `--init-guard`: no INIT read first); `va_class` prints `INIT (readable: nk_decomp)`; `reader-coverage.md` row 6 updated. Rule 15: M1.2f and M8.E1 closed as superseded (the other five were closed by H81); M1.4 was already re-opened by M1.21 (rule 15). Builds B/C not run (EXP Follow-ups).
  - Depends: — (H51: `tools/nk_decomp.py` works on IMG256)
  - Goal: make the stored bytes of every compressed section an ordinary input. Today `cerom.py decompress` says `UNSUPPORTED` 245 times, the L3 harness maps `INIT` bytes as a guard that stops the run (M9.35), and `cmp_ind_reader` gets `inflate_mask[17]` as a declared table instead of from the image.
  - Precheck: `python3 tools/nk_decomp.py --selftest`; `python3 tools/nk_decomp.py section IMG256 --module NaviMapCC.dll --index 1` prints `r0=0x484 OK` (0.7 s); `python3 tools/nk_decomp.py check IMG256` (several minutes) prints the count recorded in EXP-2026-11-11-H51.
  - Scope: (1) `cerom.py decompress MODULE --section N [-o]` and `decompress --check` call `nk_decomp.decompress` (keep the pure-Python codec paths as they are); (2) `tools/l3_harness/rommap.py` gets `--init-from-image`: sec1/sec2 of the module are mapped with their decoded bytes followed by zero BSS, the IAT slots still bound to stubs, the `INIT` guard off; (3) `va_class.py` prints `INIT (readable: nk_decomp)` and `l3_precond.py`/`reader_precheck.py` stop naming M1.2f for `INIT`; (4) a cache `archive/work/decomp/<image-sha12>/<module>.secN.bin` (never committed; `.gitignore` already covers `archive/`). No new format claims.
  - Input: `tools/nk_decomp.py` (`decompress(data, file_off, psize, vsize)` returns `(r0, dest)`; `r0` = stored length, `0xffffffff` = error), `tools/cerom.py` `comphdr --all --json` (`uncompressed_len` per section is the expected `r0`), `tools/l3_harness/rommap.py` (M9.35 `--bss-zero/--init-guard`), `tools/chunk_decoder_l3.py` (`INFLATE_MASK_VA 0x00574de0`, `sec1_table`).
  - Hints: the routine is slow in PySh4 (about 6 kB of output per second: `Navi.exe` sec1 16 s, sec2 15 s) — decode once and cache. The three stack arguments sit at `sp+16`: `skip=0`, `step=1` (2 gives the same bytes on the four sections tried), `block=0x1000`; without them the function returns `-1` at once, which is what stopped M8.E1. Build B is byte-identical on the EU and US cards, so the same routine serves both. H51 already compared `inflate_mask[17]` at `0x00574de0` with `2^n-1`: equal — replace the declared table by the image bytes and drop the HYPOTHESIS note in `targets.json`.
  - Done when: `cerom.py decompress --check` reports `245 OK` (or lists the exceptions) with `r0 == uncompressed_len` for each; `runner.py run cmp_ind_reader` passes with `--init-from-image` and no declared table; `mmain_reader` and `drstr-sub_00419350` probes are re-run with real `INIT` bytes and the next stop is recorded; `selftest.py` passes; `reader-coverage.md` row 6 updated.
  - Stop: if a section returns `-1` or a length different from `comphdr`, record module/section/psize and keep it as an exception; do not patch the routine.
  - Re-opens on merge (rule 15): closes **M1.2f, M1.2g, M8.E1, M8.E1c, M9.29, M9.30, M1.2e** as superseded (set them `done` with `Result: superseded by H51/M1.19`), and re-opens **M1.4** (see M1.21).
  - Claims: C-3500–C-3509

- [x] **M1.22b — Harden `fn_match` to ≥90 % on the cited EU readers: exact instruction-level diff and the EU→US census EXP**
  - Status: done · Owner: task/m1.22b-us-census · Critical: yes · Pair: required
  - Depends: M1.27 (leaf path), M1.28 (frozen EU→US fixture), M1.31 (the leaf census: a percentage over `635 leaf` mixes complete leaves with `0x400`-cap-truncated rows and no-`rts` stubs)
  - Goal: `fn_match match IMG256 US256 --module Navi.exe` maps **5/13** cited readers UNIQUE (SE 2026-11-13); the done-when needs ≥90 %. Find out whether the 8 NOMATCH are real code differences or a matcher weakness (e.g. a missing reloc class, a pool word that is an address in one build and a constant in the other, or a callee index that shifts).
  - Precheck: `python3 tools/fn_match.py match archive/head256.img /tmp/opencode/us256.img --module Navi.exe --va 0x003f5194 0x0041c7dc 0x0041c990 0x0041c044 0x0041a438 0x00419350 0x004125a8 0x003fbed8 0x0040b358 0x003bc960 0x003f632c 0x003f61bc 0x00542250` (make US256 with `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img`; SHA-256 must be `70d945d8…`) reports `unique: 5 … nomatch: 8`; the same command with US replaced by IMG256 reports `unique: 13, nomatch: 0` (positive control).
  - Scope: `tools/fn_match.py` hash/diff (`record_digest_map`, the one-hop call-order propagation) and its CLI; the EU→US table for the cited VAs; `tools/l3_harness/targets.json` gains `build` on every target (`"eu2011"` now; `"us2011"` when a US VA is used); `docs/format/firmware.md` EU→US rows. Not: matching every function (that is the census, below).
  - Input: `tools/fn_match.py`, EXP text (none yet — this task writes it), `tools/pdata.py`, `docs/format/firmware.md`; H51 §4 EU/US sizes (`7,596` vs `7,520` records).
  - Hints: the three UNIQUE hits already form the `.cmp` chain (`0x0041c044→0x0041c990→0x0041c7dc`), so the matcher works on contiguous code; the NOMATCH cluster is the REFER family, which the EXP says has real differences (`XMD` vs `TMC`, `INDEX001`). Disassemble `0x0041a438`/`0x00419350` in both builds and compare instruction-by-instruction before touching the hash — the POINT walker `0x003f5194` is a pdata GAP (leaf), so it needs the leaf path, not a record hash. If a NOMATCH is a genuine rewrite, record it as `DIFFERENT` with the first differing instruction pair, not as `NOMATCH`.
  - Done when: an EXP has the full census (module name, sizes, section hashes, identical/different/only-in-one for both builds), the 13-VA table with `UNIQUE`/`DIFFERENT`/`AMBIGUOUS` and the reason for each non-unique, and either ≥90 % UNIQUE or a per-function `DIFFERENT` justification that the done-when accepts; `targets.json` has `build`; M9.10/M9.12 name the US build as the S1/S2 gate.
  - Stop: if the REFER family is rewritten rather than moved, publish the census + the differing-instruction pairs, mark M1.22 blocked on "the US reader must be re-located" (a new M3 task), and stop.
  - Result: EXP-2026-11-16-M1.22b-eu-us-census; C-3620–C-3629. Of the 8 NOMATCH, **6 are matcher misses**: identical masked instruction-form stream with a unique US twin and only literal-pool values moved (`0x0041a438→0x0044219c`, `0x00419350→0x004410b4`, `0x004125a8→0x0043a378`, `0x0040b358→0x00433458`, `0x003bc960→0x003ec274`, `0x003f61bc→0x0041eb1c`); `0x003fbed8` (ADDRE resolve) is a **genuine rewrite** (`bf` vs `mov.l @(pc),r3` at `+0x16c`, 8 vs 7 calls, no form twin) and `0x003f5194`'s leaf stays one pool word (`0x4e8→0x4d8`). Census `unique 5 / different 7 / nomatch 1`; EU-vs-EU control `13/13 UNIQUE`. `fn_match` gains `_pool_only_twin` (33 selftest checks incl. two false-positive shapes), the frozen fixture re-pins the six rows and replays `13 rows, 0 mismatch`, `targets.json` gains `build` (validated), and M9.10 now names the US POINT walker/accessor VAs. The old `≥90 % UNIQUE` floor is **not met** (`38 %`) and is reported as a data-layout metric — 12 of 13 cited readers are located, 5 exactly and 7 with a justified same-code/different-constant pairing.
  - Claims: C-3620–C-3629

- [x] **M1.45 — Decompile map of telematics (`Telema.exe`, `ComMid.exe`, `Telema*CC`, `Cws_Apl`, `Prb_Apl`, `DCM_API`)**
  - Status: done · Owner: task/m1.45-telematics-endpoints · Critical: no · Pair: solo
  - Depends: —
  - Goal: side track. The Carwings client: how it reaches the TCU (`COM3:`/`COM4:` over USB) or a phone (`COM8:` Bluetooth dial-up), server names and URLs in the binary, the request types. Useful for OpenCarwings users: what the unit can fetch (points of interest, routes, charging spots) and in what format.
  - Precheck: UTF-16 and ASCII strings of `Telema.exe` contain a host name or `http`.
  - Scope: static, EU2011 and US2011 (build A differs). Output `docs/firmware/telematics.md`: transport table, endpoint list, message types. No network traffic is generated.
  - Done when: the page lists the endpoints and for ≥ 3 request types the builder function VA and the payload fields readable from strings.
  - Stop: do not contact any server; credentials or identifiers found in the binary are not copied into the repo.
  - Claims: C-6470–C-6479
  - Result: EXP-2026-11-21-M1.45-telematics-endpoints; 5 request types (CreateSession/SendData/SetAPN/CloseSession/GetOperatorInfo) with EU+US builder VAs and string-readable payload fields; endpoint table both builds; gate 4 pass

- [x] **M3.3 — Run the `.ind` reader on the 8 `ind_mutate.py` variants**
  - Status: done · Owner: — · Critical: yes
  - Depends: M3.2, M9.5
  - Done when: accept/reject per variant is recorded and compared with
    `cmpind.py`.
  - Claims: C-5340–C-5349 (was C-840–C-849; fresh block for this run)
  - Result: EXP-2026-11-20-M3.3-ind-variants-l3.md (done, C-5340–C-5344). EU2011 full-layer L3 run (`cmp_read_l3.py batch`, firmware's own `.ind` parser) on the 8 ADDRE001 variants vs `cmpind.py`: 6 agree (both reject: `size_20000`/`size_8000` at the `chunk_size` compare, `off0_1`/`off_last_m1`/`off_last_p1`/`off_last_0` in inflate); 2 disagree — `count_p1` read byte-identical, `count_m1` returns 79,360 B wrong from byte 65,536 with no error (D1 is a writer obligation). The `cmp_ind_reader` fragment target cannot judge `.ind` variants (harness-built table).

    `CMP.LST` (count, order, sentinel, leading `u32 = 0x2f`), which M5.6 must
    satisfy.
  - Input: EXP-2026-11-06-M3.4 (`Navi.exe` `0x00419684`, `0x0041ba90`,
    callers `0x00419d24`/`0x00419ca0`, filename table `0x00179cf8`); M3.4 had
    no disassembler: `apt-get install binutils-sh4-linux-gnu` works here,
    then `sh4xref.py --calls` and `objdump -b binary -m sh4`.
  - Done when: each function's file API calls (named via C-1710/M1.9), the
    buffer it reads into, and every compare on the read data are listed with
    VAs in `drstr.md`; or the EXP shows the data is handed to another
    module (named) without checks.
  - Claims: C-1860–C-1869
  - Result: EXP-2026-11-06-M3.10-drstr-cmplst-fns (C-1860–C-1869). `0x0041ba90` (CMP.LST) does only `fopen`/`fclose` — no content read/compare (existence check). `0x00419684`→`sub_00419350` reads/parses DRSTR001 (heap `*0x009cfcdc` ≤`0x77220`, stack 40B) with size/read checks at `0x419388,0x4193da,0x4193e4,0x419462-0x419468,0x419496-0x4194a6` (`_modlu`/`>=200` caveat noted) but **no 0x2f root / 40-node / 324-entry compare found** (C-1864, strengthens C-859); `sub_004191d0` bounds `entry_count+1 < 15000` at `0x41920a`. All in `Navi.exe`, coredll ordinals named. `drstr.md` updated.

- [x] **M4.16d — TMC location→segment placement via `TFTBL`/`reception.dat`**
  - Status: done · Owner: task/m4.16d-tmc-segment-placement · Critical: no
  - Result: EXP-2026-11-20-M4.16d-tmc-reception-table-codes — `TMC/reception.dat` lists the card's 14 (CC, LTN) pairs, one per RDSTM table; a table code is `ord(CC hex digit) << 8 | LTN` (14/14 listed, 14/14 codes carry the RDS CC of the country their records land in; shuffled countries max 8/14). With M4.16b (C-5400/C-5402) the chain (CC, LTN, location code) → RDSTM table → record → MAPAL node is closed. `TFTBL001` is absent on 2011 cards (C-122), not tested. `tools/tmc_reception.py`. C-2320–C-2323.
  - Done when (set at close, the block had none): every `reception.dat` (CC, LTN) maps to exactly one RDSTM table whose placed records lie in the country with that RDS CC, above a shuffled-country control — met.
  - Step: P3
  - Depends: M4.16b, M4.7
  - Goal: if `RDSTM001` is TMC (C-882), test placement through the TMC
    location table chain rather than raw row bytes.
  - Claims: C-2320–C-2329 (was C-1960–C-1969, already used by M4.19)

- [x] **M5.11 — End-to-end: one generated tile on an accepted card image**
  - Status: done · Owner: task/m5.11-one-generated-tile · Critical: yes
  - Note (M9.13, 2026-11-20): software evidence for the factory-backed splice: the firmware's mount reads a `tilewriter.py --factory` `B48R058R` (two ways in a `0x2046` directory) read-for-read like the factory tile (C-3253). A fresh-container tile is not readable: every directory must be backed by the fixed length the firmware reads (`0x8100` for section 1 level 1; C-3256, C-3257). Check a card's tile with `python3 tools/datask_l3.py mount … --position LAT,LON --replace MAPAL001/<tile>=<file> --json B.json` then `diff`. Corrected by M5.56 (DRSTR001 clamp; tilewriter pads), C-5832/C-5833.
  - Depends: M5.4, M5.6, M5.10, M5.12b, M4.20 (accept facts: M2.3, M2.5, M2.12
    done; M2.15 and M9.6/M2.4 for the exact map-code bytes)
  - Goal: the Phase-2 milestone — turn OSM input into a card image that the
    firmware would accept, with one tile actually regenerated from OSM (not
    just a verbatim rebuild).
  - Input: `osm_ingest.py` (M5.1), the mesh splitter (M5.2), the tile writer
    (M5.4), the tree rebuild (M5.6), `mkcard.py` (M5.10); the acceptance
    facts from M2.3/M2.5/M2.12 and `realcheck.py`.
  - Done when: a script (or documented pipeline) produces `out.img` from a
    Dolnośląskie extract where exactly one tile is OSM-generated and the rest
    is factory; `cardcheck.py --image` + `l2check.py` pass; and an EXP checks
    `out.img` against every known accept/reject gate (HDD_INFO fields,
    map-code comparator inputs, attestation, SD lock) and states, per gate,
    pass / not-applicable / cannot-verify-offline. No vendor bytes committed.
  - Claims: C-2330–C-2339 (was C-1970–C-1979, already used by H9)
  - Result: EXP-2026-11-19-M5.11-one-generated-tile. `out.img` `b88a31f4…f95fe3` = EU 2011 card + `B48R058R` with dir (76,940) level 1 regenerated from the committed Dolnośląskie fixture `m5.37-splice.osm` (sandbox has no OSM host; real-extract run is M5.44): 42,542 diff bytes, all in the tile's clusters; `cardcheck --image` + `l2check` (incl. `--graph-tiles`) PASS; readback 18/18 within 1 m. Gates: 7 PASS (HDD_INFO, map-code check 1 ACCEPT in L3 under the declared unit record, `0x06000000` copy, version block, manifests, zlib, FAT), 2 not-applicable (`HDD_CHK.ATT`, SystemSD/UserSD check), 3 cannot-verify-offline (MapDBVer range, SD lock, tile reader L3 BLOCKED).

- [x] **M5.17 — `LCTBL001.DAT` file builder (H11 G5)**
  - Status: done · Owner: task/m5.17-lctbl-builder · Critical: yes
  - Step: P3
  - Depends: M3.15, M4.18
  - Goal: `lctbl_records.py` re-encodes streams, but no tool builds the
    catalog plus the 500-record pages, so a Poland card cannot carry Polish
    street and place names.
  - Input: `tools/lctbl_records.py` (all 517 streams byte-identical),
    `lctbl_names.py`, `rdstm.md` §LCTBL, M4.18's open items (header `+7..+13`
    attributes, the 0–22 B footer, the 500-record page cap), M3.9 collation
    (`OBJ_Sort_cmpStr` weight table) and the CP1252 rule.
  - Done when: a builder writes a complete `LCTBL001.DAT` for a synthetic name
    set, the header/catalog/page framing matches the factory layout, the
    output passes L1/L2, and an unchanged input rebuilds byte-identically;
    the sort order matches the firmware's weight table (`--selftest`).
  - Claims: C-2410–C-2419
  - Result: EXP-2026-11-20-M5.17-lctbl-builder. `tools/lctbl_build.py` decodes the whole file (sector addresses, 3-list catalog, per-table B-tree index, ≤500-record zlib pages, page directories at the end — the old "0xff padding" was the directories) and writes it from `{header, flag word, tables: code, location codes, records}`: EU (247,089 records) and US 2011 (303,023) rebuild byte-identically; a synthetic 5-table Polish set (3,668 records) builds deterministically, passes L1 `cardcheck` (stale-DRSTR control FAILs) and the non-golden L2 checks (unchanged rebuild: L2 PASS); L3 `0x003f61bc`/`0x003f5d98` read the generated catalog descriptor + records, 3,668/3,668 fields == model (C-2410–C-2417). Sort clause: the file order is the location-code B-tree key (selftest refuses unsorted codes); names are not collated in the file (rdstm.md rule 4), so no weight-table order is applied. Index lookup / page loader at L3 → **M5.60**.

- [x] **M5.29 — Dolnośląskie one-tile pipeline: OSM→IMF→mesh→tile→L1+L2+gate report**
  - Status: done · Owner: — · Critical: yes
  - Note (M5.34, 2026-11-17): Done when met on the factory root via M5.34 (EXP-2026-11-17-M5.34-parcel): routing the test geometry into `0x2046` directory `(76,940)` instead of `0x2146` `(76,941)` lets the pipeline complete; `cardcheck` + targeted `l2check` PASS, one tile + `DRSTR001.DAT` differ. The H51 blocker note below is kept as history.
  - Note (H51, 2026-11-11): **Unblock: M5.34** — the factory rerun (PR #171) failed because the test ways fell into a `0x2146` directory; route them into one of the `0x2046` directories instead. PM decision on the open boundary question: `0x2146` directories stay verbatim (preserve-only) for this milestone; that is not a reason to hold the run.
  - Note (rerun, 2026-11-09): unblock (EU2011 factory image available, `archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` `105e2032…`) satisfied; factory-backed rerun attempted. PR #171's content (`--factory-root` mode + EXP) was merged to `main` by the PO on 2026-11-16 and its branch closed; the task stays `blocked` on M5.34, not on the branch.
  - Depends: M5.1, M5.2, M5.4, M5.6, M5.10, M5.28
  - Goal: produce the first repeatable Poland compiler milestone: one OSM-generated tile swapped into a factory EU card, validated offline at L1+L2 with an explicit acceptance-gate report (operationalizes M5.11).
  - Precheck: `tilewriter.py --selftest` 68/68 OK; `rebuild_manifests.py --selftest` OK; `one_tile_pipeline.py --selftest` OK (`selftest.py --only one_tile_pipeline` PASS). `cardcheck`/`l2check` have no `--selftest` flag (recorded as skips). Factory EU tree: EU2011 is available on this machine via `fetch_image.py` (rule 11); IMG256 lacks MAPAL001.
  - Scope: `tools/one_tile_pipeline.py` (stdlib + existing tools, `--selftest` on synthetic data, `--factory-root` for the factory path) produces `out` with exactly one OSM-generated tile `MAPAL001/B48R058R.DAT` (`mapping=provisional-v0`, via `roadclass_v0`/`tilewriter`); rest of the tree factory/verbatim; rebuilds manifests; runs `cardcheck`/applicable `l2check`; emits honest gate report. No vendor bytes committed.
  - Input: compiler tools, `hddinfo.py`, M2.18 if landed, `profiles/dolnoslaskie-test.*`, reader-coverage matrix, EU2011 factory root.
  - Done when: `cardcheck` and applicable `l2check` pass; report lists per gate (HDD_INFO/MAP CODE bytes, DRSTR/MMAIN/CMP.LST/.ind, tile round-trip/structure, section 4, manifests): `PASS`/`NOT-APPLICABLE`/`CANNOT-VERIFY-OFFLINE`/`NEEDS-L3`; EXP names tile, fixture SHA-256 or extract metadata, states provisional classes and firmware acceptance unknown (rule 13).
  - Stop: factory tile/tree not obtained/fetched (rule 11) — synthetic-only path produced; real-image/factory run marked `blocked` with missing input named.
  - Blocker: factory-backed rerun extracted the EU2011 tree (480 files) but `tilewriter --factory` refused `MAPAL001/B48R058R.DAT` directory `y=76 x=941` kind `0x2146` (slot-table, record boundaries not safe to mutate; M5.22 `PRESERVE_ONLY_DIR_KINDS`). Tile not generated; Done when not met. Same input failure hit the synthetic scaffold (MMAIN/section alignment; `clarion_tile.read_tile` `struct.error`).
  - Unblock: **M5.34** (route the test ways into a `0x2046` parcel so the factory-backed run completes). Re-open M5.29 when M5.34 merges (rule 15). Alternative unblocks: extend tilewriter/M5.22 for safe `0x2146` mutation with verified round-trip evidence, or produce a factory-coherent OSM tile without unsafe mutation and prove cardcheck/applicable l2check pass.
  - Result: EXP-2026-11-09-M5.29-one-tile-pipeline (synthetic-only, blocked); rerun EXP-2026-11-09-M5.29-factory-rerun (factory-backed attempted, unblock satisfied, blocked on `0x2146` tilewriter safety, C-3054). `mapping=provisional-v0`, rule 13 (L3/L4/L5 unknown). PR #171 closed 2026-11-16 after this content was merged. Done when met by M5.34 (EXP-2026-11-17-M5.34-parcel).
  - Claims: C-3050–C-3059

- [x] **M5.60 — L3: the `LCTBL001` index lookup and page loader read a generated file**
  - Status: done · Owner: task/m5.60-lctbl-index-l3 · Critical: no · Pair: solo
  - Step: P3
  - Depends: M5.17 (done)
  - Goal: M5.17 ran only the record walk (`0x003f61bc`/`0x003f5d98`) on a generated `LCTBL001.DAT`; the B-tree lookup (location code → ordinal), the page-directory read and the zlib page load that hand the walk its record were not executed, so rule 13 "accepted" holds only for the record bytes.
  - Precheck: `python3 tools/lctbl_build.py l3 archive/head256.img FILE` passes (record walk); `python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x003fbed8` (search type 1 opener, M3.28) is `START`.
  - Scope: EU2011 build A `Navi.exe`; candidates below the opener `0x003fbed8`/`0x004125a8` that read 0x1000-byte pages keyed by `u32 ordinal + BCD4` (signature from the writer's inverse, `lctbl_build.py`, not the format doc).
  - Input: EXP-2026-11-20-M5.17-lctbl-builder (C-2410–C-2417), EXP-2026-11-19-M3.28-file-openers, `docs/format/rdstm.md` "File structure (M5.17)".
  - Done when: an L3 run looks up a location code in a generated file (`lctbl_build.py synth`) and returns the record the model holds for that code, with a negative control (a code absent from the file is not found).
  - Stop: if no reader of the index pages is found after the opener subtree and its indirect calls are enumerated, record the candidates and block.
  - Claims: C-6140–C-6149
  - Result: EXP-2026-11-20-M5.60-lctbl-index-l3. `tools/lctbl_lookup_l3.py` runs the whole lookup in PySh4 (EU2011): request `0x14e4` sub 1 (country code, database number, location code; table code = hex digit of the country << 8 | number) → catalog → B-tree index pages → page directory → zlib page inflated by `HDL_MapTblTask` (`0x14b8`/`0x14b9`) → answer `0x14fb`. On a `lctbl_build.py synth` file 4/4 held codes return the model's record and 3/3 absent codes are not found; factory file 4/4 agree; a flipped index key and a damaged record page both break the agreement (C-6140–C-6149). Open: the real country/database numbers for Poland; an absent table is served from the first table (observed).

- [x] **M5.1 — OSM ingest to IMF**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Note: reopened by the 2026-11-06 review because `tools/osm_ingest.py` was
    not on `main` at a8a1994; it is merged together with this status change.
  - Depends: —
  - Goal: read a Dolnośląskie `.osm.pbf` (Geofabrik) and write IMF v1 with
    drivable roads and the tags the compiler needs.
  - Input: `docs/research/intermediate-format.md`, `tools/imf_check.py`.
  - Done when: `tools/osm_ingest.py` reads `.osm` XML and `.osm.pbf`
    (stdlib PBF decoder or a documented optional dependency) and produces IMF
    that passes `imf_check.py` on a synthetic fixture generated by its
    self-test (a few ways, a roundabout, a one-way, a turn restriction). The
    region run is M5.1b, because OSM hosts are blocked here (C-1716).
  - Result: `tools/osm_ingest.py` reads `.osm` and `.osm.pbf` and emits
    identical IMF that passes `imf_check` (EXP-2026-11-06-M5.1-osm-ingest).
  - Claims: C-1030–C-1039

- [x] **H77 — `fn_audit`/`claims_check` do not skip fenced code blocks, so an EXP that quotes a citation becomes a live citation**
  - Status: done · Owner: task/h77-skip-fenced-code · Critical: no · Pair: required
  - Depends: M1.26 (done: the l3 scope and its overlay), H76 (done: the l3 image assertion)
  - Goal: in H71 the driver's first EXP draft put the probe text `Goal: fn 0x<VA> probe` inside a fenced block; `fn_audit.citations_markdown` has no fence state, so the EXP became a live l3 citation and the gate went `CORPUS STALE: 1 new` (full `selftest.py` RED). It was worked around with a `$VA` placeholder — a workaround that every future EXP writer must know. Fenced blocks are the documented way to quote a command; a scanner that treats their contents as prose will keep producing this class (the same failure in the docs scope is silent, because `docs/format/*.md` has few fences). This is a *policy* decision, so it is a pair, not a solo edit.
  - Precheck: `python3 -c "import re;t=open('docs/experiments/EXP-2026-11-16-H71-evidence-spans.md').read();print(bool(re.search(r'(?s)\`\`\`.*?fn 0x[0-9a-f]{6,8}.*?\`\`\`?',t)))"`; append a fenced `fn 0x<start>` to a copy of a `docs/format/*.md` and run `python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet` — today it prints `CORPUS STALE: 1 new` for a fenced line.
  - Scope: `tools/fn_audit.py` (`citations_markdown` and the `TODO.md` open-block scanner) gain a fence state: a `\`\`\`` (or `~~~`) block in an EXP/`docs/format` file is skipped, while a `TODO.md` task block keeps its current rule (TODO.md has no fences). Refresh the docs base and the l3 overlay only for the citations the change *removes* (if any), with an EXP that states the before/after counts. Not: changing the `strict` kind rules, the US-build skip, or the pin path.
  - Input: `tools/fn_audit.py` `citations_markdown`/`citations_open_tasks`; H71's `Correction` (the workaround); M1.26's `--scope l3` overlay; `docs/experiments/TEMPLATE.md` (the fenced commands).
  - Done when: a fenced `fn 0x…` appended to a copy of `docs/format/firmware.md` (and to an EXP) does **not** change either `--corpus` verdict (exit 0, unchanged counts); an unfenced one does (`CORPUS STALE: 1 new`, exit 1); `python3 tools/fn_audit.py --selftest` covers both, and `python3 tools/selftest.py` stays green; a before/after count of fenced citations (if any) is in the EXP.
  - Stop: if a fence-aware scanner would change any committed snapshot row, say so in the EXP and ship the scanner with a *new* overlay rather than silently rewriting the frozen one (H69's rule).
  - Claims: C-4000–C-4009
  - Result: EXP-2026-11-20-H77-skip-fenced-code; C-4000–C-4003. `fn_audit.fenced_lines` (any-indent ``` / ~~~ fences, an unclosed fence hides nothing) is applied in `citations_markdown` for both disciplines; `TODO.md` open blocks keep their rule (they are not fence-aware, H115); the docs-base scan of `TODO.md` is. Docs base: 0/552 citations were fenced, so it is unchanged. l3 overlay: 159/1176 rows were fenced (START 126, GAP 18, INSIDE 10, UNMAPPED 5), so under the Stop rule a new overlay `fn-audit-l3-corpus-2026-11-20.json` (1017 rows at measurement, 1045 after the last `main` merge) ships as the gate/selftest default; the 2026-11-16 overlay is kept at `main`'s state when H77 merged (1204 rows, SHA-256 `c80330acac8b7839cfa38681ff7c865f80477d095c9750e3e4a7f430803f83d8`); not re-synced after H77 (`--write-snapshot` refuses its name). A fenced probe in `firmware.md`, an EXP or `map-tiles.md` leaves both verdicts at exit 0; unfenced, it gives `CORPUS STALE 1 new`, exit 1. `fn_audit --selftest` has 78 checks. `claims_check` unchanged: it has no citation scanner and its evidence rules read fenced commands; the title's mention is superseded by the Scope. Navigator fixes: EXP §Corrections after navigator review.

- [x] **H81 — Close the seven task blocks that carry an H51 "superseded" note**
  - Status: done · Owner: task/h81-close-superseded · Critical: no · Pair: solo
  - Depends: M1.19 (its `Re-opens on merge` line already promises to close them, but it is open and unowned); H51 (`nk_decomp.py` decodes 245/245 build-A sections, which made them moot)
  - Goal: seven task blocks still carry `Note (H51, 2026-11-11): **superseded — do not take.**` — M1.2e, M1.2g, M8.E1c, M9.29, M9.30 are **open** and M1.2f, M8.E1 are **blocked** (printed by the ID/status probe in the Precheck). Every PO/SM pass re-reads and re-skips them, and the board's open count counts five of them as takeable work. M1.19 is meant to close them on merge, but it is open and unowned, so nothing will.
  - Precheck: `python3 - <<'EOF'` probe below prints the seven IDs with their status; `grep -c 'superseded — do not take' TODO.md` counts every occurrence including this block's own two Quote/Goal lines, so it is not a selector; the probe below is (7 task notes at the time of writing): run the probe instead of the raw grep.
    ```bash
    python3 - <<'EOF'
    import re
    L=open('TODO.md').read().split('\n'); i=0
    while i<len(L):
        m=re.match(r'^- \[[ x]\] \*\*([A-Za-z0-9.]+)',L[i])
        if m:
            j=i+1; body=[]; st='?'
            while j<len(L) and not re.match(r'^- \[',L[j]):
                body.append(L[j])
                s=re.search(r'Status: (open|in progress|blocked|done)',L[j])
                if s and st=='?': st=s.group(1)
                j+=1
            if any('superseded — do not take' in b for b in body) and m.group(1)!='H81':
                print(m.group(1), st)
            i=j
        else: i+=1
    EOF
    ```
  - Scope: TODO.md only — set the seven blocks to `Status: done` with `Result: superseded by H51/M1.19 (nk_decomp.py decodes 245/245 build-A sections; see M1.19)`, **or** `Status: blocked · Unblock: M1.19` if the PO prefers them visible until M1.19's wiring lands. Keep the history note; do not delete blocks; do not touch M1.19's own block (its "re-opens" sentence already covers the closure).
  - Input: TODO.md blocks M1.2e/M1.2f/M1.2g/M8.E1/M8.E1c/M9.29/M9.30, M1.19's `Re-opens on merge` line, `tools/nk_decomp.py`, EXP-2026-11-10-M9.35-sec1-load-model.
  - Hints: M1.19 bundles the real closure (it re-opens M1.4); this task only makes the board honest before M1.19 starts. Prefer `done · superseded` for the five open ones — they are not takeable work and must stop inflating the open count — and leave the two blocked ones as `blocked · Unblock: M1.19` if their own unblock chains still point elsewhere.
  - Done when: the probe prints no `open` row among the seven; the board totals change by exactly the number moved (open −5, done +5, or blocked +5 and open −5); `python3 tools/todo_check.py` and `--strict` show no new errors.
  - Stop: if M1.19 merges first and closes them, mark this done as superseded with a one-line Result; do not fight the merge.
  - Result: EXP-2026-11-16-H81-close-superseded; C-4040–C-4044. Five of the seven H51-superseded blocks were `open`; they are now `done` with `Result: superseded by H51/M1.19` (history note kept, no block deleted), so the probe prints no `open` row among the seven and the board moves `open 108→103`, `done 59→64` (`blocked` unchanged at `28`). The two `blocked` ones (M1.2f, M8.E1) keep their own `Unblock:` chain, not M1.19, which would be a false unblock. `todo_check` OK; `--strict` 69→66 (M1.2e's three firmware fields drop out, nothing new). H81's own stale `grep -c` count is corrected: `10`, not `11`.
  - Claims: C-4040–C-4049

- [x] **M1.24 — `sh4literal`: one literal-pool scan that reports referenced vs unreferenced 32-bit words**
  - Status: done · Owner: task/m1.24-sh4literal · Critical: yes · Pair: required
  - Depends: — (uses `sh4dis`/`pdata` when the image is given)
  - Goal: three recent negative results ("never read") rest on ad-hoc sec0 literal surveys pasted into EXPs (M3.13 pass-3; M3.11c/M3.15 earlier) and are not reproducible from the repo. Replace them with one tool so "literal X appears in no pool" is a command, not a story.
  - Precheck: `python3 tools/sh4scan.py --selftest` passes; `grep -n "def load_literals\|class.*pool\|literal" tools/sh4xref.py` shows the pool resolver to reuse.
  - Scope: new `tools/sh4literal.py` (`--selftest`): parse a module's executable sections, collect every PC-relative `mov.l @(disp,PC)`/`mova` target (32-bit pool words) and report per word `VA, word, referencing instructions[]`; query modes `find WORD` / `--range LO HI` / `--unreferenced`; `--module M --image-start S` for a real image, `--json` for EXPs. Also report a module's literal pools **inside decoded INIT sections** when `nk_decomp` can decode them, so "sec1 was not searched" is visible. Not: a disassembler (reuse `sh4dis`).
  - Input: `tools/sh4dis.py` (operand decode), `tools/sh4xref.py` pool logic, `tools/sh4scan.py`, `tools/pdata.py` (function ranges), `tools/nk_decomp.py` (INIT bytes).
  - Hints: M3.13's `:;:` (`0x3a3b3a`), `01 f4 00 00` (`0x0000f401`/`0x01f40000`), `4e 20 00 00` (`0x0000204e`/`0x4e200000`), `0x0000ff00`, `0x0000c000`, `0x0000a000` are the regression corpus — the tool must reproduce M3.13's "0 references" for the first three and its "1 reference" for `0xc000`. Positive control: a known-referenced literal (e.g. `LCTBL001.DAT` address at `0x0017a1f8` loaded by `fn 0x004125a8`).
  - Done when: the tool reproduces the M3.13 corpus in an EXP, including whether the constants appear in **decoded sec1/sec2** (a column the pass-3 EXP lacked); `--unreferenced` on `Navi.exe` sec0 gives a count; selftest covers direct/PC-relative/pool-in-data and a false pool word; `--parent-of VA` prints the true enclosing `fn` start from the pool walker's own operand data (so `0x0041c7e8` prints `0x0041c7dc`), and that command is the re-check H63's `Pin:` line names.
  - Stop: if `nk_decomp` cannot decode a target section, print `NOT SEARCHED (section N)` — never fold it into "absent".
  - Claims: C-5980–C-5989 (was C-3630–C-3639; fresh block for this run)
  - Result: EXP-2026-11-20-M1.24-sh4literal; C-5980–C-5988 (C-5989 reserved). `tools/sh4literal.py` (`find`/`bytes`/`--range`/`--unreferenced`/`--parent-of`/`--parent-audit`, `--json`, 21-check `--selftest`) on `archive/head256.img` (`92aa525d…`) `Navi.exe` EU2011 sec0 + decoded sec1/sec2 (5,712,528 B): M3.13 corpus reproduces — `0x0000f401`/`0x01f40000`/`0x0000204e`/`0x4e200000` 0 pool words module-wide, window `0x003f5000`–`0x003f7000` `0x0000ff00` 0 loads and `0x0000c000` 1 (`0x003f56ec`); module-wide `ff00` 42 / `c000` 82 loads (pass-3 counts are window-scoped); `:;:` 5 occurrences (4 sec0 + 1 decoded sec1 `0x005621d5`), none pointed to; decoded sec1/sec2 add no reference. `--unreferenced` 13,015 not PC-relative-loaded words in 12,562 pool blocks (navigator fix: 3,276 `pointed` by a held address, 9,739 unreferenced; `--h118-compare` 135,975 shared pool halfwords with `fn_match.pool_slots`, 836/189 differ). `--parent-of 0x0041c7e8` → `0x0041c7dc`, `0x00542256` → `0x00542250` (H63 Pin re-check), walker vs `.pdata` 7,507/7,596 agree (1.17 % differ). New: `0x4e20` is a 16-bit `mov.w` literal twice in the window (`0x003f51c2`, `0x003f5bcc`), outside C-970's 32-bit search (C-5986).

- [x] **M1.26 — `fn_audit --scope l3`: turn H52's audit into the standing PR gate the M1.25 plan skipped**
  - Status: done · Owner: task/m1.26-fn-audit-scope-l3 · Critical: yes · Pair: required
  - Depends: M1.25 (`fn_audit.py`), M1.23 (pdata-backed labels), M1.30 (frozen snapshot, the gate base), M1.29 (corrections must not count as `INSIDE`, else the gate can never reach zero), H69 (refreshed snapshot + the `moved`-only policy this gate must name, PO 2026-11-16), H72 (the `AMBIGUOUS` candidate-set gate, done)
  - Goal: M1.25 ends with `fn_audit --scope docs` over `TODO.md`, `docs/format/*.md` and `targets.json`. The M9/M3 board cites dozens more VAs inside task blocks (`l3_harness` targets, EXPs, `_l3.py` constants); without this, the next mid-function entry (H51 found three) ships unnoticed. Close H52 with an automated check rather than a one-off table.
  - Precheck: `python3 tools/fn_audit.py --selftest` passes; `python3 tools/fn_audit.py archive/head256.img --scope docs` reproduces the H52 three (`0x0041c7e8`, `0x00412bee`, `0x00542256`) as `INSIDE` with their true starts; `python3 tools/fn_audit.py --scope l3 archive/head256.img` exits `2` (flag absent, the gap this task fills).
  - Note (SE 2026-11-15): after M1.29 a correction line (`0x00542256 → fn 0x00542250`) is `CORRECTED`, not `INSIDE`, so 0x00542256 (ctx-only today) leaves the failing set; keep the Precheck honest by naming the VAs that still appear as a live `fn`/`sub_`/target when this runs, not the literal three.
  - Note (SE 2026-11-16): the gate must run on **M1.30's frozen corpus snapshot**, not the live `TODO.md` — the count moves with prose (an H63 edit alone shifted the pin-popped summary `INSIDE 5→10` at `26f33cd`). Add M1.30 to this task's `Depends` when claiming, and make `--scope l3` accept the snapshot as its base plus the l3 files as an overlay.
  - Note (SE 2026-11-16, third — post-H72/M1.27 coherence): the overlay design is still sound but two things must be stated when claiming, not left implicit. (1) **Candidates gate:** H72 shipped `verdict_differs` comparing the `AMBIGUOUS` candidate set, but the committed snapshot is `AMBIGUOUS 0`, so the gate is **unexercised on real rows** (H72 EXP Follow-ups). The `--scope l3` overlay is the first source of `AMBIGUOUS` rows; its Done-when must refresh the snapshot with at least one `AMBIGUOUS` row and prove the candidate-set comparison fires on it, else M1.26 ships green over an untested gate. (2) **`moved` policy under an overlay:** the frozen base is already `125 moved` on `main` (H69/H72 prose drift); the l3 overlay adds its own rows whose `line` numbers move whenever a task block is edited, so "moved warns, new/gone/verdict fails" must apply **per source** (docs base vs l3 overlay) — do not let l3 line churn either fail the gate or silently fold into the docs `moved` count. The histogram the gate prints must name both totals; the H74 path/count check is what catches a claim that types one of them. Nothing here re-opens H72 or M1.27; it pins what the overlay must show.
  - Note (SE 2026-11-16, second): the retro/TL text says the gate runs with `--live-check`, but **no such flag exists** — the live comparison is on by default and only `--no-live-check` turns it off (`tools/fn_audit.py:1164`). Also, today's `compare_live` re-scans only `--scope docs`, so an `--scope l3` gate would report staleness for the docs base and be **blind to drift in the l3 overlay** unless the overlay gets its own live comparison. The committed snapshot is already `moved`-stale on `main` (97 `TODO.md` lines, H69) — the gate must name whether those moves fail it. Plan the overlay's staleness check and read H69's policy before wiring the gate; do not cite `--live-check`.
  - Scope: extend `tools/fn_audit.py` with `--scope l3` scanning `tools/l3_harness/targets.json`, `docs/format/firmware.md`, `docs/experiments/EXP-*.md` (parsed only, EXP files are read-only) and every `0x…` in open task blocks. Exit 1 on `INSIDE`. Not: editing the citations (H52) or re-deriving readers.
  - Input: `tools/fn_audit.py` (M1.25 output), H52 table format, `pdata.py` (census), EUs/US builds.
  - Hints: EXPs cannot be edited (append-only); report their stale VAs in a file `docs/research/fn-audit-2026-11-13.md` instead. `GAP` needs a direct `bsr`/`jsr`/pool caller to count as a leaf; H51's `sh4xref` `fn` heuristic is not evidence (the sh4xref↔pdata mismatch rate is H52's Done-when item — M1.25 did not measure it).
  - Done when: `--scope l3` covers ≥ 3 corpora (targets, firmware.md, open task blocks), reproduces the H52 three where they remain live citations (after M1.29 a correction line is `CORRECTED`), is wired into `tools/selftest.py` as a skipped fixture plus a synthetic `INSIDE` that must fail, and the audit file lists every remaining `INSIDE`/`DATA/UNKNOWN` with a task ID that fixes it. H52 closes with the applied table (rule 15).
  - Stop: if a corpus has no reproducible parser, list it as `NOT SCANNED` with the reason rather than guessing.
  - Claims: C-3660–C-3669
  - Result: EXP-2026-11-16-M1.26-fn-audit-scope-l3; C-3660–C-3666 (C-3667–C-3669 reserved). `--scope l3` covers targets 1, `firmware.md` 59, EXPs 770 over 69 files with rows (292 EXPs on disk), open blocks 61 over 18 contributing blocks (35 citation lines of 134 open) = **891 citations / 179 unique VAs / 295 files**; on `archive/head256.img` (`92aa525d…`) `START 712, INSIDE 81, CORRECTED 11, GAP 75 (leaf 75), AMBIGUOUS 5, UNMAPPED 7`, exit 1, `--fix-list` 21 lines; `--scope docs` unchanged (313 citations, `INSIDE 0`, exit 0). An open block is scanned with the docs discipline (a live `fn`/`sub_` label, a correction `ctx` with its own arrow pair, or a `CORRECTION_ONLY` pin), not every `0x…`, so a bare data address/path/range/string or US-build VA is skipped and **no open block contributes an `INSIDE`**; the round-1 `1269 citations / INSIDE 137 / 59 unique` was a classifier false-positive storm (proved: appending `0x00d53500` to an open block stays green, a live `fn` label of `0x0041c7e8` exits 1). `US_BUILD_STARTS` (six US-2011 Navi VAs, C-3487/M1.28) are skipped for every kind in both scopes. The 81 `INSIDE` occurrences are 21 unique VAs (17 `fn`, 4 `sub_`), all in append-only EXPs and marked `accepted data/append-only` in `docs/research/fn-audit-2026-11-13.md`; `0x00542256`/`0x003f5fc2` resolve through the new pin path (`CORRECTED`), `0x00413af4` is `correction-only`. Overlay frozen to `docs/research/fn-audit-l3-corpus-2026-11-16.json` (`6adb8d5b…`, 891 rows/295 files, reproducible byte-for-byte). `--corpus BASE --overlay L3` applies H69 **per source**: `CORPUS DRIFT: DOCS BASE: 0 new / 0 gone` (125 moved, warn) + `CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved`, exit 0; `--overlay` without `--corpus`, a non-l3 overlay and a hash mismatch each exit 2. H72 is exercised on real rows: the overlay's 5 `AMBIGUOUS` rows over 4 VAs all hold an `INSIDE` candidate, and `--selftest` proves a live candidate that gains `INSIDE` is `CORPUS STALE` exit 1 while unchanged candidates stay moved-only exit 0. Wired into `tools/selftest.py` as `fn_audit_l3` (synthetic `INSIDE` fails / `START` passes; block discipline and strict markdown assertions, no image) and `fn_audit_l3_image` (`skip_unless`; asserts no data address and no US start in the overlay). No `--live-check` flag exists (live compare is default, `--no-live-check` disables); `fn_match.py`/`pdata.py` untouched.

- [x] **M1.34 — The `AppLaunch.dll` launch table: how `Navi.exe` is started and what gates it**
  - Status: done · Owner: task/m1.34-applaunch-table · Critical: no
  - Result: table base `0x03bb2330` (EU2011 = US2011), 112 records × `0x310` B via getters `0x03bccb84`/`0x03bccb88`, walker `fn 0x03bcc5b0`, filter `fn 0x03bcc564`; EU `Navi.exe` = record #81 `0x03bc1b40` (type 4, area `0x00020000`, waits 80/20/3/4/40/94/82, id `0xa2`). `fn 0x03bcc078` creates `Navi.exe` suspended and resumes it only if the error flag `0x01f733f0` is clear after id 82, which `MountStorage` (`fn 0x03bd224c`) signals after `SDC1:` → `DSK1:` mount → check 1 `fn 0x03bd2ad8` → check 2 `fn 0x03bd2ce4`. Corrected the USA/Euro area masks (C-5350). Tool `tools/applaunch_table.py`; `docs/research/rom-registry.md` updated. EXP: `docs/experiments/EXP-2026-11-20-M1.34-applaunch-table.md`. Claims C-3528, C-3529, C-5350, C-5351.
  - Depends: M1.21 (done)
  - Goal: M1.21 found that `Navi.exe` is started by `AppLaunch.dll` (build B, loaded as `Drivers\BuiltIn\AppLch`) from a compiled-in table, not from the registry, and that the same module opens `\SystemSD\VER_INFO\HDD_INFO.TXT` and prints `MapDBVer : %d <= [%d] <= %d`. Name the table's record layout, the function that walks it, and the order of the SD/map-version checks before `Navi.exe` starts, so a generated card's `VER_INFO` can be checked against the gate.
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img sections AppLaunch.dll` shows an uncompressed code section at `realaddr 0x03bb1000` (EU2011); `python3 tools/sh4xref.py archive/head256.img AppLaunch.dll --image-start 0x3e00200 --to 0x03bc92f0` (`HDD_INFO.TXT`, EU2011) lists two loading functions (EU2011, see EXP-2026-11-19-M1.21), while `--to 0x03bc0f54` (`\windows\Navi.exe`) prints `No literal pool holds` — the Navi entry is reached through a data table, not a code literal (M1.21 session, 2026-11-19).
  - Scope: build B `AppLaunch.dll` (EU2011; US2011 build B is byte-identical); the launch table and the `HDD_INFO.TXT`/`MapDBVer` path. Not: the error screens already in `docs/format/validation.md`, not Navi.exe itself.
  - Input: EXP-2026-11-19-M1.21-filesentry-decode (string VAs `0x03bc0f54`, `0x03bc92f0`, `0x03bc9360`, EU2011), `docs/research/rom-registry.md`, `docs/format/validation.md` (the AppLaunch router), `tools/sh4xref.py`, `tools/sh4dis.py`, `tools/nk_decomp.py pdata --module AppLaunch.dll`.
  - Done when: an EXP names the table base, record size and the fields for the `Navi.exe` record (EU2011 VAs, function starts checked with `nk_decomp.py pdata`), and the function that opens `HDD_INFO.TXT` with the comparison it makes; `docs/research/rom-registry.md` gains the result.
  - Stop: if no static reference to the table is found after the string-pool and `.data` search, record the negative with the positive control (a `\Drivers\Launch\SD` reference) and block on an L3 run of the router.
  - Claims: C-3528–C-3529 (and C-5350–C-5351 from the reserve)

- [x] **M1.35 — What `AppLaunch.dll` asks `SDC1:` before the mount (`0x80032000`/`0x80032004`), and who signals wait id 94**
  - Status: done · Owner: task/m1.35-sdc1-ioctl-wait94 · Critical: no
  - Depends: M1.34 (done)
  - Goal: M1.34 found that `MountStorage` (`fn 0x03bd224c`, EU2011) opens `SDC1:` and sends `DeviceIoControl 0x80032004`/`0x80032000` with retries (`fn 0x03bd2044`) before `DSK1:` is mounted, failing with error `0x80` `NO SD CARD`; `SD UNLOCK NG` (`0x81`) is never dispatched there. Name the handler of these two IOCTLs in `SDHC.dll` (build B) and say whether it is the CMD42 unlock, and find the signaller of ACM wait id 94 that every non-JP `Navi.exe` record waits for.
  - Precheck: `python3 tools/sh4dis.py archive/head256.img AppLaunch.dll --image-start 0x3e00200 --va 0x03bd2044 --count 80` shows the two IOCTL literals (`0x03bd20f8`, `0x03bd2108`, EU2011); `python3 tools/cerom.py --image-start 0x3e00200 archive/head256.img sections SDHC.dll` lists an uncompressed code section.
  - Scope: build B `SDHC.dll` `IOControl` dispatch for `0x8003xxxx` and the `ACM9:` driver's `SET_ID` callers outside `AppLaunch.dll`. Not: the lock password value (never written in the repo).
  - Input: EXP-2026-11-20-M1.34-applaunch-table, `tools/applaunch_table.py`, `tools/sh4xref.py`, `tools/nk_decomp.py pdata`.
  - Done when: an EXP names the `SDHC.dll` function that handles `0x80032000` and `0x80032004` (pdata START, EU2011) with the SD command it issues, and the module that sends `IOCTL_ACM_SET_ID` with id 94 (or a negative with the `AppLaunch` id-82 sender as positive control).
  - Stop: if the `SDHC.dll` IOControl dispatch is not found after the literal search and an export walk, record the negative and block on an L3 run of `fn 0x03bd2044`.
  - Claims: C-5352–C-5359
  - Result: done — EXP-2026-11-20-M1.35-sdc1-ioctl-wait94. `SDC1:` = `CSDCMain` in `SDHC.dll` (EU2011 = US2011); `fn 0x039b4498` dispatches `0x80032004` to `fn 0x039b4850` (port state: 2 inactive, 4 `DSK1:` active, 8 failed, 1 no card, `|0x80000000` if unpowered) and `0x80032000` to `fn 0x039b4664` (insert/remove request: port power + wake the load thread). Neither issues CMD42; the unlock runs inside the `DSK1:` activation (`fn 0x039b4b18` → `CDSKMain::Init` → `fn 0x039b6ac4`), which then sets ACM id 37. Id 94: no SET_ID sender in images A+B+C of either build (`tools/acm_id_scan.py`: 0 of 71/72 calls; controls 37, 22, 82 found), so `Navi.exe` waits out its 30 s (C-5352–C-5357; C-5358–C-5359 unused).

- [x] **M3.2 — `.ind` handling: `chunk_size` and seek vs scan**
  - Status: done · Owner: — · Critical: yes
  - Note (M9.44, 2026-11-19): measured on the running layer: the `.ind` is read as a 16-byte header and then the offset table (one read of up to 2,048 bytes), and only the chunks covering the request are read from the `.cmp`, by seek (C-4643). `.ind` +4 is not compared with the `.cmp` size (C-4646).
  - Unblock: M3.2b's re-run (the chunk engine and its caller), or M1.2f when
    the `.ind` layer turns out to be in `Navi.exe` sec1.
  - Blocker: `.ind` chunk reader (chunk_count/chunk_size/chunk_offset consumer) not identified; `fn 0x00418748` is a resolver only. See EXP-2026-11-06-M3.2-ind-handling.
  - Depends: M3.1
  - Goal: answer from code whether `chunk_size` sizes a buffer or is
    compared against `0x10000`, and whether the reader seeks by offset or
    scans for `78 9c`.
  - Input: M3.1 functions; `docs/format/cmp-ind.md`; `tools/ind_mutate.py`.
  - Done when: both answers are in `cmp-ind.md` with VAs.
  - Claims: C-5330–C-5339 (was C-830–C-839; fresh block for this run)
  - Result: EXP-2026-11-20-M3.2-ind-handling-l3.md (done, C-5330–C-5334). EU2011 L3 run of the whole compressed layer (`tools/cmp_read_l3.py`: mount `0x41bc98`, open `0x41b780`, seek `0x41b8a4`, read `0x41b954`, host ops): (a) `chunk_size` compared with the mount word at `0x41c92a` (0x8000/0x20000 rejected before any `.cmp` read; mount word 0x20000 rejects the factory file; both 0x20000 -> 79,360 wrong bytes), sizes nothing; (b) seek to `chunk_offset[first]` + one read (POINT010 seek `0x234d7f`), `78 9c` decoy + shifted index still correct, `off_last_m1` -> -1, no scan. Factory ADDRE001/POINT010 byte-identical. Static answers were already in `cmp-ind.md` (M3.2b); L3 paragraph added.

- [x] **M4.11 — `LEV3456R.DAT` coarse levels 3–5 semantics**
  - Status: done · Owner: task/m4.11-lev-coarse · Critical: no
  - Result: EXP-2026-11-06-M4.11-lev-coarse (`tools/lev3456.py`; level 5
    62/62 records decoded and recompressed, whole 76,066,304-byte file
    byte-identical; levels 3/4 region-identical with 1,677/41 preserved)
  - Depends: —
  - Goal: what the overview levels contain and how to regenerate them from
    OSM (needed for zoomed-out display).
  - Done when: `map-tiles.md` describes levels 3–5 content and a rebuild of
    one level from decoded records is byte-identical.
  - Claims: C-990–C-999

- [x] **M4.47 — Find the POINT chain locator (where a chain base and its table are recorded)**
  - Status: done · Owner: task/m4.47-point-chain-locator · Critical: yes
  - Depends: — (M5.26 done: chain tables and `tools/point_pair_regen.py` on `main`)
  - Goal: M5.26 can re-pack a POINT page chain only inside its own slot (24–248 B of slack per name chain) because nothing known tells the reader where a chain base and its chain table are (C-2955). Find that locator so a regenerated chain can move or grow and mass OSM name sets fit.
  - Precheck: `python3 tools/point_pair_regen.py --selftest`; `python3 tools/point_pair_regen.py scan EU/REFER001` reports 99 tables / 0 unresolved; `python3 tools/point_pair_regen.py locator EU/REFER001` reproduces `NOT FOUND (best 4/33)` with control 33/33 (the search space already excluded).
  - Scope: decoded `REFER001/POINT0nn.DAT` of EU and US 2011 (44 files): the 0x200–0x2000 directory area (`ffff 0000 0201` record at `0x1000`, 6-byte cells near `0x820`/`0xe80`), the `4e 20 00 00` index chains, the area after the tables; then, if the file does not hold it, the firmware: the caller(s) of `fn 0x003f5194` (EU2011) and the `0x00d53500` buffer table (C-2184/C-2540) that hands it a page. Name the build next to every VA. No writer change beyond `point_pair_regen.py`.
  - Input: EXP-2026-11-19-M5.26-point-pair-regen (`chains_detail` in `scan --json` gives every base/table/end), `docs/format/refer.md` §POINT page chains, `tools/point_walk_l3.py`, `tools/sh4xref.py`, `tools/nk_decomp.py pdata`.
  - Hints: the three bases differ between files while the `0x1000` record's words do not scale with them — try differences between chains (base2000 − table1000 etc.), counts of records/pages (1000/page), and sums of `comp_w` of *other* chains. A differential is strongest: move one chain in a synthetic copy and run the L3 POINT walk path.
  - Done when: an EXP names the field(s) (offset, width, unit, base) that give each chain base and table offset in 44/44 files with a negative control (a shuffled value fails), and `point_pair_regen.py` gains a relocation mode that moves a chain to the end of the `.DAT` and updates that field, with its selftest; or the EXP shows the locator lives in firmware/another file with the reading VA (EU2011) and a control.
  - Stop: if neither the file search (directory + index chains) nor the firmware caller path of `fn 0x003f5194` yields it after both are searched, record the scopes searched and set blocked on the first M3 reader task that executes the POINT open path in L3.
  - Claims: C-5390–C-5396 (C-5397–C-5399 given to M4.52)
  - Result: EXP-2026-11-20-M4.47-point-chain-locator (C-5390–C-5396). Structures are addressed by a BE `u32` block address `(off/0x800)<<8 | (off%0x800)/0x100`; directory cell `0x82a` (6-byte cells at `0x800..0xf06`) → the field-dictionary record holding base references (`addr, length_w`) at `+0x2e` (1000) / `+0x13c` (400) and table references (`addr, length_w, per_page`) at `+0x19a` / `+0x1b6`; cell `0xeba` → the 2000 chain's record `+0x24` / `+0x94`. One layout in 44/44 files, 264 references each unique, 132/132 chains verified through it; shuffled and plain-unit values reach 0 chains. `point_pair_regen.py relocate` moves a chain to the end of the `.DAT` (selftest 37 checks); EU POINT010 takes 1,000 and 6,199 real names M5.26 refused. Firmware reader of the reference not located → M4.52.

- [x] **M4.52 — Run the POINT open path on a relocated name chain (who reads the chain locator)**
  - Status: done · Owner: task/m4.52-point-locator-reader · Critical: yes
  - Depends: M4.47 (done)
  - Goal: M4.47 found the chain locator in the file (directory cell `0x82a` → field-dictionary record → base reference `+0x2e`) and `point_pair_regen.py relocate` moves a chain to the end of the `.DAT`, but no firmware code was seen reading the reference (C-5396 is a hypothesis). Rule 13 needs the reader to read a relocated chain.
  - Precheck: `python3 tools/point_pair_regen.py --selftest`; `python3 tools/point_name_accessor.py --selftest`; `python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x0040ee4c` prints `START` or `INSIDE`.
  - Scope: EU2011 `Navi.exe` (name the build next to every VA, then US2011): the loader that fills header-table entry `+44` (`0x0040ee4c`'s 100 × 80 table, `0x0140e240` EU2011, M3.11c) with the dictionary block, the code that reads the directory cell at `0x800` and the reference at dictionary `D+4` (`D = C + 2*u16[C+2]`, the header `fn 0x003f56bc` reads), and the code that turns `start_w` into a page read. No writer change.
  - Input: EXP-2026-11-20-M4.47-point-chain-locator, EXP-2026-11-19-M3.11c-point-name-accessor-l3, `tools/d53500_writer.py`, `tools/point_name_accessor.py`, `tools/sh4xref.py`.
  - Hints: the base reference is a block address: look for a `shlr8`/`shll8` pair or a byte load of `addr & 0xff` (the data is BE on an LE CPU, so the reader may build it from bytes); the `mov #11`+`shad` sites `0x003f6ae6`/`0x003f6d5c` (EU2011) log `(@(12,r) << 11) + @(16,r)`, a sector/offset pair of a request struct — its writer is a candidate.
  - Done when: an EXP names the VA (EU2011 and US2011) that reads the base reference, and an L3 run of that path on `relocate` output reads record 1 of the moved name chain at its new base (positive) while a pair with the reference left at the old base does not (negative).
  - Stop: if the loader is reached only through an IAT import that M9.35 cannot bind, record the call chain and set blocked on that binding task.
  - Claims: C-5397–C-5399
  - Result: EXP-2026-11-20-M4.52-point-locator-reader (C-5397–C-5399, C-5396 updated). The base reference is read by the POINT page loader `fn 0x003fe2d4` EU2011 / `0x00426480` US2011 (callers `0x003ffce0` / `0x00427e1c`), which decodes `D+4` with the block-address leaf `0x0040f00c` / `0x00436f58` and requests `base + 2*start_w`; cell `0x82a` is decoded by the header parser `fn 0x003f930c` / `0x00421c3c`. `tools/point_locator_l3.py` (selftest 21) runs parser + loader + walker in PySh4: on `relocate` output 6/6 runs (EU2011 5, US2011 1; pages 0/1/15) request the new base and record 1 matches; with the reference left at the old base 6/6 request the old base and REJECT; factory 5/5. Declared: dictionary record placed in header-table `+64` (`0x003fc518` not run), host inflate.

- [x] **M5.19 — `RDSTM001` writer (H11 G7)**
  - Status: done · Owner: task/m5.19-rdstm-writer · Critical: no
  - Result: EXP-2026-11-20-M5.19-rdstm-writer — exit (b) fails: the rows are region-tied (a copied file resolves 6,910/200,987 refs against a renumbered `B48R058R` section 2, the re-pointed one 200,190/200,987 = factory). Exit (a) met for the TMC rows: `tools/rdstm_write.py` (selftest 20 checks) rebuilds the EU 2011 `RDSTM001.DAT` byte for byte from records + triples + `(parcel, node, link)` targets (set-1 4 × 4 boxes, entries in location-code order; file order fails), and EU2011 `fn 0x003f61bc`/`0x003f5d98` in PySh4 walk written rows exactly for 24 + 500 factory and 24 synthetic Polish rows (controls 0). Link-group firmware L3 waits for M4.49's reader VA; the 16-bit record swap and the `0x80000` chunk limit are hypotheses. C-2430–C-2436.
  - Step: P3
  - Depends: M4.16b (record framing), M3.7
  - Goal: every `RDSTM001` row is copied verbatim from the factory card today;
    a Poland card needs rows that describe Polish segments.
  - Input: `rdstm.md` (twelve TMC fields with getters, C-882–C-889),
    `rdstm_record.py`, `rdstm_schema.py`, `0x003f61bc` field directory,
    EXP-2026-11-06-M4.16b.
  - Done when: a writer produces a file the firmware decoder walks with the
    expected values for ≥ 20 rows (an L3 target), or the EXP shows that
    copying is correct because the rows are region-independent.
  - Claims: C-2430–C-2436 (C-2437–C-2439 spare)

- [x] **M5.52 — `mutate_refer_poi.py --resize` must update the record's field-length bytes, or the firmware reads a truncated name**
  - Status: done · Owner: task/m5.52-resize-field-len · Critical: yes
  - Step: P4
  - Depends: M3.11c (done — the accessor and the field-length bytes)
  - Goal: M3.11c found that the firmware finds a POI name through the per-record field-length bytes, in words, plus the file's field dictionary, not through the `ff ff` framing. `resize_name` only rewrites `len2`. After a different-length rename the accessor still returns the old length: US2011 record 0 renamed `HANA HEALTH CENTER`→`HANA HEALTH CENTERXX` reads back as name `HANA HEALTH CENTER` and address `XX4590@HANA HWY` (EXP-2026-11-19-M3.11c-point-name-accessor-l3, C-5117). Make `--resize` update the field-5 length byte too, and refuse a delta that is not a whole number of words.
  - Precheck: `python3 tools/point_name_accessor.py run archive/us256.img --cmp <US POINT010.DAT.cmp> --ind <…ind> --build us2011 --rename "HANA HEALTH CENTER=HANA HEALTH CENTERXX" --expect "HANA HEALTH CENTERXX"` → `mismatch=1`, `result: FAIL` (the defect).
  - Scope: `tools/mutate_refer_poi.py` (`resize_name`, `verify_resize`) and its selftest; the length byte location comes from C-5115 (field area at `rec + 2*(hi+lo+8)` of `u16[rec+10]` for header class 3/2; `(n+1)/2` words of length bytes, n from the dictionary). Not: page budget, `.cmp` re-encode.
  - Input: `tools/point_name_accessor.py` (the L3 check), C-5110–C-5117.
  - Done when: the precheck command exits 0 with `ok=1000 of 1000` and the expected name on a +2-byte and a −2-byte rename, and `resize_name` refuses a record whose header class it cannot place.
  - Stop: if a record class other than 3/2 needs renaming and its length byte cannot be located, refuse it and record the class count.
  - Result: EXP-2026-11-19-M5.52-resize-field-len.md (done). `--resize` places field 5 like `fn 0x003f56bc`/`fn 0x003f5e10` (EU2011; length of field f = byte `loc+f`), requires the old text inside field 5, patches `len2` and the field-5 length byte, refuses odd deltas and unplaceable records; `--census`: 2000/2000 records class 3, all placeable. Accessor (US2011 `0x0041ec8c`, EU2011 `fn 0x003f632c`): US rec 0 −2/0/+2/+10 B and EU rec 0 −2/+2, rec 1 +2 → whole new name, address unchanged, `ok=1000 of 1000`, PASS; pre-fix +2 `mismatch=1` (precheck), old-name expectation FAIL, odd/address renames refused. The M9.39 US mutant `ea2d0e0f…` has the same stale byte at rec 500 (`mismatch=1`); the fixed CLI writes `34fb3aab…` (`ok=1000`) → new M9.54 (re-pin). selftest 17/17.
  - Claims: C-5260–C-5265 (C-5266–C-5269 handed to M9.54)

- [x] **M8.B1 — INTC model** (`0xff802000…`, `0xff804000…`, from
  `OEMInterrupt*` and the ISR at `VBR+0x600`). Done when a TMU0 interrupt is
  delivered and acknowledged.
  - Status: done · Owner: task/m8.b1-intc-model · Critical: no
  - Depends: M8.A2
  - Done when (made concrete 2026-11-20, the original line is kept above):
    on the EU2011 head (physfirst..physlast loads) `-M ze0 -d int` shows
    `exception 0x400 [interrupt]`, the firmware's TMU0 ISR runs (`in_asm`),
    TCR0.UNF reads clear afterwards and the interrupt does not re-enter;
    plus a synthetic shim control whose delivery count drops to 0 when INT2
    bit 1 stays masked.
  - Result: EXP-2026-11-20-M8.B1-intc-model (C-1310–C-1313). Patch
    `tools/qemu-ze0/patches/ze0-0003-hw-sh4-ze0-intc-tmu.patch` (INTC/INT2
    model + TMU ch0–2 at `0xffd80000`; `sh_intc` compares level-tracking
    sources with SR.IMASK). Real kernel: one INTEVT `0x400` in 60 s, ISR
    `fn 0x8803cb34` clears UNF, no re-entry; shim 70/5 s (ack), 2 (no
    ack), 0 (masked). The TMU0 level had to match the kernel's IntrPrio
    (1): the SH7785 field 28:24 gave a 7.5 M-entry storm (C-1312). Tool:
    `tools/ze0_intc.py`.
  - Claims: C-1310–C-1319

- [x] **M8.B3 — RTC/time** (`OEMGetRealTime`).
  - Status: done · Owner: task/m8.b3-rtc-time · Critical: no
  - Depends: M8.A2
  - Done when (made concrete 2026-11-20; history: "the date read is
    deterministic"): `OEMGetRealTime` located (EU2011 VA) with every input
    named; it reads no hardware register (or that register is modelled);
    two or more `-M ze0` runs give the identical date; plus a positive
    control (`OEMSetRealTime` of a valid date reads back) and a negative
    one (an invalid date is refused).
  - Result: EXP-2026-11-20-M8.B3-rtc-time (C-1330–C-1333).
    `OEMGetRealTime` `fn 0x880400a8` is a software clock over RAM words
    seeded from `nk.exe` data (copy entry 0): power-on date 2009-07-10
    07:10:00, identical across boots; no MMIO, so no QEMU RTC model. The
    kernel calls it 63× in boot from `fn 0x880453b0` (Unix-seconds
    conversion); set/get round-trip and a month-13 refusal as controls.
    Tool: `tools/ze0_rtc.py`.
  - Claims: C-1330–C-1339

- [x] **M8.B6 — Kernel debug text on the debug UART (no gdbstub needed)**
  - Status: done · Owner: task/m8.b6-debuglog-uart · Critical: no · Pair: solo
  - Depends: M8.A6 (SCIF model at `0xffe46000`, done), M8.B5 (F1 boot, done)
  - Goal: today the kernel's debug strings never reach the SCIF: `KernelStart` and every `NKDbgPrintfW` go through `fn 0x880404f4` → AstLog (`0x88044478`, EU2011) with the `DebugLog` path gated off (`0x89e613b0`/`0x89e613b4`), so a 60 s boot writes 0 serial bytes (M8.A6, C-1280–C-1283) and M8.B5 had to read the text over the gdbstub (`tools/ze0_dbgmsg.py`). Make the same text appear on `run.sh --serial` so every L4 run has a plain log, and so long boots (M8.C rows, M8.E4) need no breakpoint per string.
  - Scope: find what sets the `DebugLog` gate and which output routine it enables (static: callers of `0x880404f4`, readers/writers of `0x89e613b0`/`b4`; the OAL `OEMWriteDebugString`/`OEMWriteDebugByte` pair, which in CE normally writes the debug UART). Then pick the least invasive way to turn it on, in this order: (a) a board/boot argument the OAL already reads (registry, boot-args block, a strap the `ze0` machine can present); (b) a `ze0` machine option that presents the gate value at boot; (c) a documented one-word guest patch applied by `run.sh` (never committed vendor bytes, only VA + old/new word). Not in scope: changing what the kernel prints, or the gdbstub tool (keep `ze0_dbgmsg.py` as the cross-check).
  - Done when: one `-M ze0` boot of EU2011 IMG256 (`run.sh --serial`, `-icount shift=0,sleep=off`) writes the kernel debug text to `WORK/serial.log`, and for the first 200 lines it equals what `tools/ze0_dbgmsg.py run` captures for the same boot (diff = 0, or every difference explained); the boot still reaches F1 (M8.B5 checks 1–3). Negative control: the same boot without the option/patch writes 0 bytes (reproduces C-1281). The EXP names the gate, its writer, and the output routine with EU2011 VAs.
  - Stop: if the debug text can only reach the UART by patching more than one code word, or the gate is set from hardware the `ze0` machine cannot model, record the path and stop (negative EXP).
  - Hints: `tools/ze0_serial.py banner`, `tools/ze0_dbgmsg.py`, patches in `tools/qemu-ze0/patches/`, QEMU binaries from M8.B5. Requested by Marek 2026-11-20.
  - Result: EXP-2026-11-20-M8.B6-debuglog-uart (C-6240–C-6243). No gate routes the text to a UART: `fn 0x880404f4` → AstLog `0x88044478`, gated (`0x89e613b0` by IOCTL handler `fn 0x88049f4c`, `0x89e613b4` by `fn 0x8804aa08`) → `L"DebugLog"` handle `0x8804048c`/`0x88044fe8`, none loads `0xffe46000` (EU2011). Patch `ze0-0007`: machine option `-M ze0,dbgmsg=0x880404f4` copies `r4`'s UTF-16 string to serial port 0, no guest byte changed; `run.sh` turns it on by default (`--dbgmsg off`) and gains `--icount`. Same boot: serial = gdbstub for 279/279 lines; `run.sh` boot 9 288 B, byte-repeatable, 2 time-derived lines differ from the gdbstub boot; option off = 0 bytes; F1 checks 1–3 still pass. Tool: `ze0_serial.py dbgcmp`.
  - Claims: C-6240–C-6249

- [x] **M8.E1 — Run the kernel's ROM decompressor as a tool**
  - Status: done · Owner: task/m8.e1-run-rom-decompressor-retry (retry 2026-11-08) · Critical: no
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` runs the kernel's own `DECOMP_SECT` in PySh4 and `cerom.py decompress --check` reports 245/245 build-A sections OK with `r0 == comphdr uncompressed_len` (EXP-2026-11-19-M1.19-kernel-decomp-wiring); no codec port or QEMU run is needed (M1.19 rule-15 closure).
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M8.E1b (VAs verified, C-2290–C-2293). Does **not** need F1: call
    the function under `-M none` + gdbstub with RAM-only state (LE SH-4).
    M8.A1 now builds a LE `qemu-system-sh4` from the pinned 8.2.7 tarball, so
    the toolchain half is done. M1.2f is the parallel Python route to the same
    two vectors — whichever lands first unblocks M1.3/M1.4.
  - Blocker (updated 2026-11-08 retry): `/usr/bin/qemu-system-sh4` 11.1.3 (LE,
    Fedora 45) is present and IMG256 `92aa525d…` obtained, but
    `cedecomp_run.py probe` fails under QEMU 11.1.3 `-M none` (P1 VA
    `0x8c/0x88xxxxx` access `E14` / steps to `0x8c010000`, `sh7785`/`sh7750r`;
    nk.exe linked at fixed 0x88xxxxxx VAs). `exp49` for verified
    `DECOMP_SECT 0x88037464` is still `NOT_IMPLEMENTED` (needs runtime call +
    kernel-context handling for WRAP, C-2293). Building repo `-M ze0` QEMU
    (phys `0x08000000` + P1/P2 aliases matching nk.exe) is blocked by missing
    `glib2-devel` (no root). No runtime decode ran. (C-1604, C-1606, C-1607)
  - Unblock: provide a `qemu-system-sh4` (LE) with `-M ze0` (or install
    `glib2-devel`/deps and run `tools/qemu-ze0/build.sh`), make
    `cedecomp_run.py` run the probe under a compatible SH4 memory map, then
    implement `exp49` via `DECOMP_SECT 0x88037464` (constructed frame) or
    stubbed `DECOMP_WRAP 0x88037590` kernel-context helpers (C-2293).
  - Note: M8.E1's initial "VA refuted" blocker was a BE endianness artifact,
    corrected by M8.E1b (C-1600/C-1603 superseded). Verified entries (LE):
    `DECOMP_WRAP 0x88037590` / `DECOMP_SECT 0x88037464` (core framing) /
    `DECOMP_BLK 0x8803a384`, loader flag test `0x88038666` in `fn 0x880385e4`.
    Use `qemu-system-sh4` (LE). DECOMP_WRAP needs kernel lock/context stubs
    (C-2293); calling SECT with an initialised frame may bypass that.
  - Result: EXP-2026-11-08-M8.E1-rom-decomp-retry-qemu11 (negative, blocked):
    qemu 11.1.3 LE present (original binary blocker resolved) but probe fails on
    QEMU 11.1.3 `-M none` P1 mapping/compat for nk.exe 0x88xxxxxx VAs; `exp49`
    `NOT_IMPLEMENTED`; `-M ze0` build blocked by missing `glib2-devel`.
    EXP-49/Navi.exe sec1+sec2/245/FILESentry runtime decode **not achieved**.
    Prior: EXP-2026-11-08-M8.E1-rom-decomp-runtime-blocked; EXP-2026-11-06-M8.E1-rom-decomp-tool (corrected by M8.E1b).
  - Done when: the two EXP-49 sections decode to the M1.2a lengths, then
    `Navi.exe` sec1/sec2 (the sections M3.2b and M3.11 need: sec1
    `psize 0x457c` / `vsize 0xff16ae`, sec2 `psize 0x8884`), then all 245
    sections and the `FILESentry` payloads (cross-check M1.3/M1.4).
  - Claims: C-1600–C-1609

- [x] **M9.11b — L3 runner: a firmware-call target kind for the chunk reader (fills `cmp_ind_reader`)**
  - Status: done · Owner: task/m9.11b-firmware-call-target-r2 · Critical: yes
  - Depends: M9.11 (firmware path and sec1 table provenance, EXP-2026-11-08-M9.11-chunk-decoder), M9.5 (done).
  - Precheck: `python3 tools/chunk_decoder_l3.py` and
    `python3 tools/l3_harness/runner.py --selftest` pass; `targets.json`
    still lists `cmp_ind_reader` unfilled/blocked. Confirm sec1
    `inflate_mask[17]` provenance is recorded in M9.11 EXP before making it
    a declared input.
  - Goal: let `runner.py` run a firmware function with memory setup (the 20-byte table,
    the stubs, the sec1 `inflate_mask` table as a named, sourced input), so that
    `targets.json` `cmp_ind_reader` runs the chunk reader on a corpus pair through the runner.
  - Scope: extend `runner.py` entry kinds/memory setup for firmware-call
    targets; declare the sec1 table as an explicit sourced input; wire
    `cmp_ind_reader` controls from M9.11. No format claims beyond plumbing.
  - Input: `tools/chunk_decoder_l3.py` `run_firmware` and its stubs; `tools/l3_harness/runner.py`
    entry kinds (`module` passes register arguments only); `targets.json`.
  - Done when: `runner.py run cmp_ind_reader` on the factory pair reports PASS and exit 0; the
    corrupt-`.ind` and swapped-field cases report as the controls in EXP-2026-11-08-M9.11-chunk-decoder; the sec1 table
    is a declared input of the entry (not a silent default), and `runner.py selftest` passes.
  - Stop: if memory-setup semantics cannot be expressed without a silent
    default table or guessed VA, block with the missing provenance named;
    do not register `cmp_ind_reader` as passing.
  - Claims: C-2940–C-2949 (was C-2157–C-2159, overlap with M9.11 fixed by H24)
  - Result: EXP-2026-11-08-M9.11b-firmware-call-target — `firmware_call` entry kind + declared sec1 `inflate_mask[17]` (VA `0x574de0` from code, values from public zlib 1.1.3, provenance disclosed, M1.2f HYPOTHESIS) fills `targets.json` `cmp_ind_reader`; `runner.py run cmp_ind_reader` on factory US POINT010 (`92aa525d…`/`48812f8c…`/`7ac54e3b…`, page `0x840ba0`) PASS exit 0 (`r0=42848`, insns 1057245); `--mutate corrupt-ind`/`swap-4-8` PASS as M9.11 controls (`r0=-1`/638, `r0=65536`/1057219). `chunk_decoder_l3 --selftest` OK, `runner selftest` OK (32), `claims_check` OK. Resolves M9.11 registration blocker; `l3check.py` untouched (M9.12).

- [x] **M9.20 — L3 plumbing: firmware entry kind, `engine_hook`, `ghidra/l3_run.py`**
  - Status: done · Owner: claude/m9.20-l3-plumbing · Critical: no
  - Depends: —
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` (pre-change
    baseline) and target M9.5/M9.3/M9.9 follow-up requirements reproducible
    from their EXPs; EU2011 head available for the synthetic/module mapping
    check per rule 11.
  - Goal: the M9.5/M9.9 follow-ups that stop a real reader from running even
    when M3 has found its VA.
  - Scope: add `module` firmware entry plumbing in `runner.py`, expose
    argument registers via `StubDispatcher.engine_hook`, add a documented
    Ghidra L3 entry script and refresh L3/README docs; cover all three in
    selftests. No Ghidra execution required.
  - Input: EXP-2026-11-06-M9.5 (`entry.kind = "module"`), EXP-2026-11-06-M9.3
    (`StubDispatcher.engine_hook(target)` reading r4–r7), EXP-2026-11-06-M9.9
    (`tools/l3_harness/ghidra/l3_run.py`, README refresh), `targets.json`,
    `runner.py`, `tools/README.md`.
  - Done when: `runner.py run` can call a function at a module VA without a
    hand-built `-device loader` map, the stub dispatcher exposes argument
    registers to a target handler, the Ghidra back end has one documented
    entry script, `tools/l3_harness/README.md` and `tools/README.md` match the
    code, and the L3 selftest covers all three.
  - Stop: if module mapping or hook semantics could not be made deterministic
    without Ghidra/runtime assumptions, record the gap as a blocker/follow-up
    rather than claiming a runnable reader verdict.
  - Claims: C-2500–C-2509
  - Result: EXP-2026-11-08-M9.20-l3-plumbing (synthetic module and hook checks
    pass; EU 2011 head: Navi.exe sec0 mapped; the walker stops at ILLEGAL_INSN
    0x4362 under big-endian decode and runs under little-endian until its
    unmapped page argument; no Ghidra run, out of scope and not installed)

- [x] **M9.26 — Revisit `POINT` byte-order / source after M9.11b registers `cmp_ind_reader`**
  - Status: done · Owner: task/m9.26-point-byteorder-revisit · Critical: no
  - Result: EXP-2026-11-20-M9.26-point-byteorder-revisit (C-2900–C-2905). New `tools/point_byteorder_l3.py run` (EU card, 9/9): decoder outputs are file order; the layer's +20 = 0 swap also hits the compressed page (not inflatable); page loader `fn 0x003fd690` runs leaf `0x003f6968` before the inflate (undo) and after it (native); the walker reads the leaf output (`parse_page` offsets 7/7; file-order page fails). C-5815 retracted for zlib pages (superseded by C-2903); C-2545(a) answered (C-2905). The task text's C-2234/C-2239 are M9.13 tile rows and are unchanged.
  - Step: P4
  - Depends: M9.11b, M3.11b
  - Goal: M3.11b found the POINT page already as native little-endian `u16` in
    the decoded buffer but left the source unknown (HYPOTHESIS C-2239, blocked
    on M9.11). M9.11's firmware path now passes byte-identically on
    factory/S1/S2 POINT010 pairs, but `cmp_ind_reader` is not registered until
    M9.11b provides a firmware-call target kind. Once registered, use the real
    decoder + the M3.11 walker to answer where the page becomes native u16 and
    whether any consumer sees file-order bytes.
  - Precheck: `cmp_ind_reader` runs on the factory POINT010 pair via the L3
    harness (M9.11b done when) and reproduces M9.11's byte-identical result.
  - Scope: POINT001/010 (factory + S2 if available); compare decoder output
    buffer layout, the walker's packed-u16 read, and the on-disk bytes. No new
    format write.
  - Done when: the EXP states, with a control, whether the decoder output is
    file-order or native, where the M3.11 walker reads from, and updates
    C-2234/C-2239 (confirm or retract) with the evidence.
  - Stop: if the registered target cannot expose the decoder's output buffer
    address, record that limit and stop; do not infer from disassembly alone
    when a runnable path exists.
  - Claims: C-2900–C-2909 (was C-2760–C-2769, collision with H26 fixed by H23)

- [x] **M9.28 — Module-entry input buffer/region mapping for real reader verdicts**
  - Status: done · Owner: — · Critical: yes · Pair: required
  - Result: EXP-2026-11-19-M9.28-input-region; `entry.input_region` maps file/literal bytes at a chosen VA with exact bounds, overlap refusal and provenance; the EU POINT walker `fn 0x003f5194` runs past its argument-pointer fault on the real EU `POINT010 0x6e06d0` page (returns `0xa8`, cross-checked against `point_walk_l3`), `--selftest` 34 checks (C-3210–C-3219)
  - Depends: M9.20
  - Precheck: `python3 tools/l3_harness/selftest.py` and `python3 tools/l3_harness/runner.py selftest` pass; reproduce M9.20's real run showing the POINT walker stops at `UNMAPPED` on its page argument (`0x0`) rather than at decode/endian. Confirm M9.24 does not already provide a generic input-buffer mapping (it focuses on coredll CRT/import binding and stack args).
  - Scope: `tools/l3_harness/` module-entry path (`runner.py`/ROM map/corpus conventions). Add a way to map a caller-supplied input buffer or file-derived bytes at a chosen guest VA for module targets, with explicit bounds and provenance in results. No firmware format claims; no Ghidra/QEMU.
  - Goal: let module-entry reader targets (M9.13/M9.14/M9.17 class, and the M9.20 walker follow-up) receive real input instead of failing at argument-pointer loads, so verdicts are limited by mapped data/stubs rather than missing input plumbing.
  - Input: EXP-2026-11-08-M9.20-l3-plumbing (open question: input region), EXP-2026-11-08-M9.14-reopen, EXP-2026-11-08-M9.17-reopen, `tools/l3_harness/runner.py`, `tools/l3_harness/rommap.py`, `tools/l3_harness/corpus.py`, M9.24 task text.
  - Done when: a synthetic module-entry target reads from a mapped input buffer and returns a verdict; at least one existing reopened/blocked reader target can be re-run past the argument-pointer `UNMAPPED` fault or reports a new, more specific blocker (faulting PC + missing data/stub named). `--selftest` covers bounds/provenance; `tools/README.md` updated.
  - Stop: if the target's input source cannot be located or bounded from available evidence, add/require an input-source locating subtask and record the missing source; do not map guessed bytes and call them a reader verdict.
  - Claims: C-3210–C-3219

- [x] **M9.44 — Virtual card: stub the three stdio wrappers once and let the firmware's file layer read a card tree ("software S0")**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes · Pair: required
  - Result: `docs/experiments/EXP-2026-11-19-M9.44-virtual-card.md` (C-4630–C-4655), tool `tools/vcard_l3.py` (`boot`, `compare`, `read`, `sweep`, `--selftest`). The whole map-file layer runs in PySh4 on a card image or tree: the firmware's own state machine mounts the factory EU card (`2/2`, 0 error-log calls, reads `CMP.LST` 19 B, `MMAIN001.DAT` `0x1000` B, `DRSTR001.DAT` in one read), builds its 40-directory / 285-file table, and serves reads through its request queue, including `.cmp`/`.ind` files inflated by the firmware zlib; all 285 files read back through the firmware equal the host's view (8,874,828 bytes compared). 10 of 13 changed cards change verdict, error log or table. Rule 13: a `cmpind_writer recompress` pair and a `drstr_ze0.build` file with a grown tile are read correctly by the firmware. Deviation from Done-when: a separate tool instead of `runner.py run mmain_reader --card-root` (the unit is the layer with its queue, not one function); imports are modelled instead of stubbing the wrappers; `targets.json` untouched; the "M5.6 rebuilt tree" is replaced by rebuilt files served through `--replace` (no rebuilt tree exists in the sandbox). New facts for other tasks: file ids are `DRSTR` positions (keep the order, C-4649/C-4650); the M3.11b byte swap is request word +20 in `0x00417eac` (C-4641); read-API record in `firmware.md`.
  - Note (H112, 2026-11-19): wrapper callers corrected (C-4621): `fread` has four callers, not five (`0x0041b2a4` is a debug dump). New fact for the target list: a map client does not call the wrappers. It calls the thin API `0x00409ba0`/`0x00409c28`/`0x00409cc8`/`0x0040b358` → `0x004192c0`, and that path reaches `OSM_TaskSend` but no stdio import (C-4629, hypothesis): the read happens in the map-file task's handlers (M3.26's message → handler table). So build the virtual card in two halves: (1) handler side — run one M3.26 handler with a request record and the stubbed wrappers, get the `(file, offset, length)` log; (2) client side — stop at `OSM_TaskSend`, print the message, and feed it to half 1. Add the tile open `0x0040b850` as the fourth target after `mmain`, `drstr`, `.cmp`; its first read log on a factory tile and on the M5.30 card's tile is the first L3 evidence for row 17.
  - Depends: M9.36 (trust the engine first), M1.19 helps (`INIT` bytes); M3.26 gives names but is not required
  - Goal: the nearest thing to putting a card in the unit that needs no unit. Today each L3 target stubs imports one by one (M9.24) and maps its input by hand (M9.28). The firmware reads map files through three wrappers — `fopen` `0x0041b3bc`, `fseek`/`ftell` `0x0041b470`, `fread` `0x0041b4f8` (EU2011, H101). Replace those three with host stubs that serve files from an extracted card tree, and the real `DRSTR`, `MMAIN`, `CMP.LST` and `.cmp` code runs on whole files, factory or generated.
  - Precheck: `python3 tools/callgraph.py users g.json fread,fseek,fopen` shows the three wrappers; `python3 tools/sh4dis.py IMG256 Navi.exe --image-start 0x200200 --va 0x0041b4f8 --count 40` shows one `fread` import call (arguments `r4…r7` are passed through or re-ordered — record which).
  - Scope: `tools/l3_harness/`: a `vcard` stub set (`--card-root DIR`): path translation from the firmware's `\SystemSD\…` strings to the tree, a handle table, `fopen`/`fseek`/`ftell`/`fread`/`fclose` semantics, a log of every `(file, offset, length)` read. Targets, in this order: `mmain_reader` (`0x0041a438`), `drstr_parser` (`0x00419684` → `0x00419350`), the `CMP.LST` opener `0x0041ba90`, then the mount state machine `0x00419ca0`. EU2011 code on the EU tree first; US2011 addresses from `fn_match` after.
  - Input: `tools/l3_harness/runner.py`, `stubs.py`, `rommap.py --bss-zero` (M9.35), `tools/callgraph.py`, the M9.14/M9.17 reopen EXPs (current stops: `wcstombs` stub for `mmain_reader`; an unmapped store for `drstr`, suspect after H51), `python3 tools/verify.py --image IMG` for the tree.
  - Hints: stubbing the *wrapper* (a function of ours-to-define contract: read its 40 instructions once) is safer than stubbing `coredll!fread` behind it, because the wrapper also does the firmware's error handling (`ferror`/`clearerr`) that we do not want to model. The read log is a result in itself: the list of `(offset, length)` the firmware reads from `DRSTR001.DAT` is the reader's view of the format, and comparing it between the factory file and our rebuilt file is a rule-13 test with no interpretation. Negative controls come free: truncate the file, flip the `0x2f` byte, remove `CMP.LST`.
  - Done when: `runner.py run mmain_reader --card-root ROOT` and `run drstr_parser --card-root ROOT` return a verdict on the factory EU tree and on the M5.6 rebuilt tree, with identical read logs or a listed difference; three negative controls each change the verdict or the log; `reader-coverage.md` rows 3–5 updated; M9.24 and M9.28 closed as covered or narrowed.
  - Stop: a stop at an `OSM_TaskSend`/message import means the function waits for another task — record the message and make that the next target; do not fake the reply.
  - Falsifier: the factory tree gives a reject verdict (then the harness, not the card, is wrong).
  - Claims: C-4630–C-4655

- [x] **M9.54 — Re-pin the M9.39 `POINT010` mutant pair with the M5.52 `--resize` (its record 500 name length is stale)**
  - Status: done · Owner: task/m9.54-repin-m9.39-pair · Critical: no · Pair: solo
  - Depends: M5.52 (done — `--resize` patches the field-5 length byte)
  - Goal: the M9.39 mutant pairs (US `.cmp` `ea2d0e0f…`, EU `e75c298f…`, C-4174) were built before M5.52, so the renamed record keeps its old field-5 length: on US record 500 the firmware accessor reads the name 2 words short (`point_name_accessor.py run` on the pair: `mismatch=1 ok=999`, C-5264). The committed command now writes US `.cmp` `34fb3aab…` / `.ind` `e525fd19…` (`ok=1000`), so C-4482 ("the committed command reproduces `ea2d0e0f…`") holds only for the pre-M5.52 tool. Rebuild both pairs with the current CLI, check them with the accessor, and re-pin the SHAs where M9.39/M9.42/M9.43 records and claims cite them (append-only: "Overtaken by a later commit" sections + new claim rows), or state per citation why the stale pair is still the right control (its walker and container results do not read field lengths).
  - Precheck: `python3 tools/point_name_accessor.py run archive/us256.img --cmp <M9.39 US mutant .cmp> --ind <…ind> --build us2011 --show 0 --expect "HANA HEALTH CENTER"` → `mismatch=1 ok=999 of 1000`, `result: FAIL` (the stale pair).
  - Scope: the M9.39 US and EU pairs only (US rec 500 `HAWAII ST GOVT FREQNTLY CLLD NMBRS`→`…XXXX`, EU page `0x6e06d0` `DROMAHAIR GARDA STATION`→`…ABCD`); records/claims that pin their SHAs (C-4174, C-4482 and the M9.42/M9.43 EXPs). Not: M9.41's target registration (other owner) beyond pointing it at the new SHAs if it cites them.
  - Done when: both rebuilt pairs give `ok=1000 of 1000` with the accessor on their build (US2011 and EU2011), the new SHAs are recorded in claim rows, and every citation of `ea2d0e0f…`/`e75c298f…` is either re-pinned or marked as the pre-M5.52 pair with a reason.
  - Claims: C-5266–C-5269
  - Result: EXP-2026-11-20-M9.54-repin-m9.39-pair (C-5266–C-5269). The current `--resize` writes US `.cmp` `34fb3aab…` / `.ind` `e525fd19…` and EU `.cmp` `979dff4a…` / `.ind` `7ee2e542…`; the name accessor gives `ok=1000 of 1000` on US2011 (`0x0041ec8c`) and EU2011 (`fn 0x003f632c`) with the whole new rec-500 name. The pre-M5.52 tool (`9316b77`) still writes the old pins, and **both** old pairs fail the accessor at rec 500 (`mismatch=1 ok=999`; EU was not known before). Walker table, wrong-build verdicts and the same-length control are unchanged on the new pairs, so only C-4482/C-4483 were stale; C-4174/C-4482/C-4483 are annotated, and EXP-M9.39/M9.42/M9.43 each have an `Overtaken by a later commit` section. M9.41 untouched (cites no pin in its own files).

- [x] **M9.6 — First real target: the map-code compare**
  - Status: done · Owner: task/m9.6-mapcode-compare · Critical: yes
  - Blocker (resolved, kept as note): M9.20 (`562215a`) added module entry kind / `engine_hook`. The earlier "no `entry.kind = module`" plumbing blocker is gone.
  - Re-opened (PO grooming 2026-11-09, rule 15): M9.20 merged. A new blocker may appear when wiring `KernelIoControl(0x0101302C)` + HDD_INFO FS stubs and the `0x01f74b30` parse cache (M2.4/M9.6 notes); record it with a faulting PC/EXP if so.
  - Negative EXP (prior): EXP-2026-11-08-M9.6-mapcode-compare.
  - Depends: — (M9.5, M2.5 done; M2.15 helps)
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` passes with module entry support; `python3 tools/cerom.py --image-start 0x200200 IMG256` can resolve the AppLaunch/Navi context used by M2.5/M2.15 (or record image start); `hddinfo_variants.py` corpus available.
  - Goal: run the real `AppLaunch.dll` compare (B `fn 0x03bd2ad8`, M2.5) on our `HDD_INFO.TXT` inputs, which unblocks M2.4. (Re-scoped 2026-11-06: M2.2's SD Import comparator checks user data, not the map.)
  - Scope: wire a runnable target for `fn 0x03bd2ad8` with `KernelIoControl(0x0101302C)` stub (`+0x60` factory 11 bytes, per M2.15) and HDD_INFO parse cache/global handling as needed; factory accept + one edited reject. No firmware format changes.
  - Input: `tools/l3_harness/runner.py`, `stubs.py`, corpus `hddinfo_variants.py` (M9.7).
  - Done when: `runner.py run` returns a firmware verdict for the factory `HDD_INFO.TXT` (accept) and for one edited line-1 variant (reject), with the stub log in the EXP.
  - Stop: if the comparator needs build-B/AppLaunch mapping, globals, or IOCTL state not reproducible from current harness inputs, set `blocked` with the faulting PC/missing stub and a new EXP (do not guess verdicts).
  - Claims: C-5140–C-5149 (was C-1680–C-1689; fresh block for this run)
  - Result: done — EXP-2026-11-19-M9.6-mapcode-compare. Target `applaunch_mapcode_compare` (`firmware_call`/`mapcode_compare_v1`, `tools/mapcode_l3.py`) runs EU2011 build B `fn 0x03bd2ad8` from IMG256: factory `HDD_INFO.TXT` → `r0=1` ACCEPT, `line1_digits_4_002` → `r0=0` REJECT (firmware log `VerInf:QSD-302-100 / HddInf:QSD-002-100`); line-2 edit ACCEPT, byte-10 edit REJECT; unit `+0x60` is a declared input (C-5140–C-5146). Re-opens M2.4 (rule 15).
