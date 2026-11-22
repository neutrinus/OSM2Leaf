# TODO history — 2026-11-22

Done tasks moved from `TODO.md` on 2026-11-22 with `tools/board.py archive`.

- [x] **H124 — `claims_check` exempts the pinned US head: `main` (and every PR) is red on a clean checkout because `archive/us256.img` is not in `PINNED_HEAD_PATHS`**
  - Status: done · Owner: task/fix-us256-claims-pin · Critical: yes · Pair: solo
  - Depends: — (H62 pinned the `US256` key; this task only lets `claims_check` see it)
  - Goal: H62 gave the US 2011 head the `US256` fetch key and its SHA-256 (`70d945d8…04da`) and H123's clean-clone CI then failed `claims_check` with `genuine missing evidence paths: 4` / `MISSING C-2141 C-2143 C-2144 C-2145 archive/us256.img` (run 44841962936, issue #418) on every pull request, while a developer tree with the file exits 0. The exemption list still held only `archive/head256.img`.
  - Precheck: `git clone . /tmp/opencode/ci-checkout && ( cd /tmp/opencode/ci-checkout && python3 tools/claims_check.py --strict --count-check; echo $? )` prints the four `MISSING` rows and `1`.
  - Scope: `tools/claims_check.py` only: add `archive/us256.img` to `PINNED_HEAD_PATHS`, name H62's key in the comment, and add a `--selftest` assertion that both pinned heads map to a real `fetch_image` alias/pin. No change to any row, no weakening of a local verdict.
  - Done when: the clean-clone command exits 0 with `genuine missing evidence paths: 0`; the developer tree stays exit 0; `claims_check --selftest` and `selftest.py --only claims_check` PASS; `tools/gate.py` 4 pass.
  - Stop: one session.
  - Result: EXP-2026-11-21-H124-us256-claims-pin; C-6490–C-6494. Clean clone (no `archive/` bytes) pre-change exit 1 with the four `MISSING` rows, post-change `genuine missing evidence paths: 0` / exit 0; the developer tree is 0 before and after; `claims_check --selftest` `OK (51 checks)`; `gate: 4 pass, 0 fail, 0 skip`.
  - Claims: C-6490–C-6494

- [x] **H19 — Re-verify the five thinnest records of the last 24 h**
  - Status: done · Owner: task/h19-reverify-thin-records · Critical: no
  - Depends: M3.19 (for the VAs that come from a scan)
  - Goal: five records carry a result in under 40 lines or with no command
    block at all (M2.6 `MapUpdate.exe` 32 lines, M3.5 tile reader 19, M3.10
    `DRSTR` calls, M9.1 module map, M8.E1). Their claims are load-bearing for
    M9.13/M9.14 and for the `MapUpdate` summary, so each needs one runnable
    check.
  - Precheck: `cerom.py sections MODULE` + `sh4xref.py --to VA` on `IMG256`;
    if a VA does not resolve to the module the record names, that is the
    finding.
  - Scope: only the VAs/counts those five records assert; no re-derivation, no
    new format work.
  - Done when: one EXP with a table `record / claim / command / reproduced?`
    for every VA and count in the five records, using committed tools, and any
    VA that does not reproduce is marked retracted with a new claim ID from
    this task's block.
  - Stop: after the table is complete; disagreements go to `claims.md`, not to
    a second round of analysis.
  - Claims: C-2520–C-2529
  - Result: done — EXP-2026-11-20-H19-reverify-thin-records. Coordinator's selection: the five shortest 2026-11-20 records (M4.16b, M4.16e, M2.19, M4.48, M3.3) were re-run with committed tools and the records' input hashes, and 19/19 rows (counts, controls, `pdata` VAs) reproduce exactly. No retraction (C-2520). The 2026-11-06 list in the Goal (M2.6, M3.5, M3.10, M9.1, M8.E1) was not covered by this pass.

- [x] **M1.4 — Extract compressed `FILESentry` payloads**
  - Tool: `cerom.py files --extract --decompress` writes stored bytes,
    classifies OK/UNSUPPORTED/FAIL and never writes a wrong-length decode
    (EXP-55, C-573); EXP-51 says the real payload is not a stdlib format.
  - Status: done · Owner: task/m1.4-filesentry-payloads · Critical: no
  - Note (M1.21, 2026-11-19, rule 15): M1.21 decodes every compressed `FILESentry` payload with the kernel routine (`nk_decomp.py files`, B 8/8, C 7/7, `r0 == rsize`); what is left here is `cerom.py files --decompress` wiring / `extract-file NAME`. The `Blocker:` line below is historical.
  - Note (H51, 2026-11-11): re-opened as **M1.21**: try the kernel routine (`nk_decomp.decompress`) on the `FILESentry` payloads.
  - Blocker: all 8 compressed build-B FILESentry payloads carry CE-LZXD block marker `0x8d80805b` and no public/stdlib `cecompress` method decodes them (0 matches, 8 UNSUPPORTED); M1.2b/c path does not suffice, so `rsize`-length decode / readable `ceconfig.h` cannot be produced without the CE-LZXD codec (M1.2f blocked, M8.E1 runtime unavailable in session).
  - Unblock: **M1.21** (the H51 re-scope: decode the `FILESentry` payloads with the kernel routine `tools/nk_decomp.py`, which already decodes 245/245 build-A sections). `M1.2f`/`M8.E1` are superseded (H51) and must not gate this task (H81 closes them). Then decode to `rsize`, add `extract-file NAME` if still desired, verify build C.
  - Depends: M1.2b or M1.2c
  - Goal: read `boot.hv`, `default.hv`, `user.hv`, `ceconfig.h`,
    `initobj.dat`, `UpdateNK.skn`.
  - Input: EXP-51 (first `u16` equals the real size for three small files;
    `boot.hv` has a step-`0x4a` table); `cerom.py --image-start 0x3e00200
    IMG files`; image C has the same names with other sizes.
  - Done when: `cerom.py extract-file NAME` writes payloads whose length is
    `real` and `ceconfig.h` is readable text (do not commit it; quote ≤ 3
    lines in the EXP).
  - Result: EXP-2026-11-08-M1.4-filesentry-payloads (extraction/characterization done; decode blocked, done-when not met; C-680–C-683).
  - Claims: C-5990–C-5999 (was C-680–C-683; fresh block for this run)
  - Result: EXP-2026-11-20-M1.4-filesentry-payloads-2; C-5990–C-5994 (C-5995–C-5999 reserved). `cerom.py files --decompress` now falls back to the kernel routine (`nk_decomp.decode_cached`, `OK` only when `r0 == rsize`; `--method kernel` skips the codecs; records gain `decoded_sha256`/`kernel`), and new `cerom.py extract-file NAME -o PATH` writes one entry at its real length or prints `REFUSED` and writes nothing. On `archive/head256.img` (`92aa525d…`) EU2011 build B 8/8 and build C 7/7 compressed rows `OK`, all decoded SHA-256s equal to M1.21; `extract-file` writes `ceconfig.h` 6,611 B (ASCII C source, `#ifndef __CECONFIG_H__`), `initobj.dat` 15,706, `boot.hv` 32,768, `default.hv` 126,976, `user.hv` 28,672, `UpdateNK.skn` 1,966,080; negative `--method lzss` → `REFUSED`, exit 1, no file. `cerom --selftest` 432 checks OK.

- [x] **H53 — make the documented `--strict` mode honest: it is implemented but the board is not clean (69 errors)**
  - Status: done · Owner: task/h53-strict-honest-2 · Critical: no · Pair: solo
  - Depends: — (this task is the board cleanup; it is what H53's own Stop anticipated)
  - Goal: H53's original premise ("`main()` does not define the flag; `--strict` is an argparse error") is stale. The flag exists (commit `9733980`) and is wired: `python3 tools/todo_check.py --strict` exits 1 with 69 `ERROR` lines over 25 firmware/search tasks (3 missing fields each), while the default run exits 0 with those same lines as `WARN`. The gap is therefore not a missing flag but a board that has never satisfied rule 14: 25 firmware/search tasks (open, blocked or already `done`) lack `Precheck`/`Scope`/`Stop`; 11 of them are `Critical: yes`. `TODO.md:248` still lists H53 as a cheap fill task and Q1's "Take first" never mentions it, so nothing will close it unless a role owns it.
  - Precheck: `python3 tools/todo_check.py --strict 2>&1 | grep -cE '^  ERROR'` prints `69`; `python3 tools/todo_check.py --strict; echo $?` prints `1`; `python3 tools/todo_check.py; echo $?` prints `0` (default still green).
  - Scope: (a) `tools/todo_check.py` only if a real bug is found in the strict path (otherwise no code change); (b) `TODO.md` only: give each of the firmware/search tasks the three fields (5 of the 25 are already `done`; a `done` task missing the fields is a warning only, so decide per task whether to backfill), or mark the ones that genuinely cannot have a `Precheck` as `Status: blocked` with the reason. Do **not** silently delete tasks or relax the rule. Add the missing `Depends:` values against the merged task IDs.
  - Input: `tools/todo_check.py` (`REQUIRED`/`strict_firmware` lists, `_parse_depends`), `python3 tools/todo_check.py --strict` output (69 ERROR + the warning text that names each task), `TODO.md` sections M1/M2/M3/M8/M9.
  - Done when: `python3 tools/todo_check.py --strict` exits 0 on `main`; `python3 tools/todo_check.py` exits 0 on the same tree; `python3 tools/selftest.py --only todo_check` passes; the EXP records the before/after ERROR count and which tasks were given fields vs marked blocked.
  - Stop: if the clean board needs a decision a role cannot make (e.g. an externally blocked task whose block owner is unknown), record those tasks under `Status: blocked · Unblock: <human>` and lower the Done-when to "no ERROR for tasks this cycle can own" — never lower the rule itself.
  - Claims: C-3650–C-3659
  - Result: done with the lowered Done-when its Stop allows ("no ERROR for tasks this cycle can own") — `docs/experiments/EXP-2026-11-20-H53-strict-honest.md`, C-3650–C-3652. `--strict` works (no checker bug); 33 ERROR / 13 tasks at `ea15563` (69 was older) → 17 after backfilling `Precheck`/`Scope`/`Stop` on M3.16, M8.D1, M8.D2, M8.E3, M8.E4, M9.2. The 17 are all on tasks held by open PRs and not edited: M1.4 #370, M3.13 #351, M3.29 #341, M8.A8 #372, M8.B6 #379, M8.C #355, M8.E2 #371; they clear when those land `done`. Default run exit 0; `selftest --only todo_check` OK.

- [x] **H97 — `l1l2_fixtures` computes `ok` without the required categories, so two NOT COVERED levels still read "OK"**
  - Status: done · Owner: task/h97-l1l2-verdict · Critical: no · Pair: required
  - Depends: H26 (the registry, done); H40/H41 own *filling* the two rows — this task is only the verdict
  - Goal: `summarize()` sets `"ok": runnable_fail == 0` and publishes `required_categories`/`missing_categories` but never consults them, so `python3 tools/l1l2_fixtures.py` prints `verdict=OK` and exits 0 while **L1 synthetic** and **L2 tile** are `NOT COVERED` (today: `runnable 6/0/1`, NC 2, rc 0). A level that never ran is silently a pass in the one L1/L2 signal CI runs on every PR (`.github/workflows/l1l2-fixtures.yml`).
  - Precheck: `python3 tools/l1l2_fixtures.py --json /tmp/opencode/l1l2.json` exits 0 with `summary.ok=true`, `missing_categories=[]` and a `NOT COVERED` in categories `L1 synthetic` and `L2 tile`; `grep -n '"ok": runnable_fail' tools/l1l2_fixtures.py` shows the line that ignores `required_categories`.
  - Scope: `tools/l1l2_fixtures.py` only: make `--json`/`--md` name the fully-NOT-COVERED required categories explicitly (`coverage_gaps: [...]`) and print a `verdict=OK (2 required categories NOT COVERED)` line, without turning NOT COVERED into a CI failure (H40/H41 make them runnable; failing CI on them now would block every PR). Exit stays 0. Add a `--require-covered` opt-in that exits 1 when a required category has zero runnable checks, for H42 to call once H40/H41 land.
  - Input: `tools/l1l2_fixtures.py` (`summarize`, `render_markdown`, `NOT_COVERED`, `REQUIRED_CATEGORIES`), H40/H41 blocks, the `l1l2-fixtures.yml` summary writer (it prints `NOT COVERED` already; keep the JSON contract additive).
  - Hints: the two honest gaps are exactly the rows H40/H41 own (`L1 synthetic` has no vendor-free builder, `L2 tile` no synthetic tile fixture) — do not invent a fixture here. Selftest's existing assertions already cover status separation (line ~468); extend it with `coverage_gaps` and `--require-covered`.
  - Done when: `python3 tools/l1l2_fixtures.py` prints the gap list and still exits 0; `python3 tools/l1l2_fixtures.py --require-covered` exits 1 on today's registry (two gaps) and exits 0 once a fixture makes both runnable; `--selftest` covers both; `python3 tools/selftest.py --only l1l2_fixtures` passes; `l1l2-fixtures.yml` keeps uploading the artifact.
  - Stop: if H40 lands first and both categories become runnable, keep the `coverage_gaps` key (now empty) and mark this task done with the measured list; do not delete the contract.
  - Falsifier: the JSON still prints `"ok": true` with a required category at zero runnable and no gap named.
  - Claims: C-4250–C-4259
  - Result: EXP-2026-11-20-H97-l1l2-verdict. `summarize()` now publishes `coverage_gaps` (required categories with zero runnable checks) and `covered`; the verdict line names the gap (`verdict=OK (1 required category NOT COVERED: L1 synthetic)`) and `--require-covered` exits 1 on it. Default exit stays 0 and the JSON keys are unchanged, so `l1l2-fixtures.yml` is untouched and keeps uploading. Measured on `origin/main` `ce5f34c`: `coverage_gaps=['L1 synthetic']` (default rc 0, `--require-covered` rc 1); the task prose's "two NOT COVERED categories" is two `NOT COVERED` *rows* — `L2 tile` is already covered by `l2.tile.class-roundtrip` (M5.36), so only one fully-uncovered category remains (Stop rule: key kept, list measured). Selftest 30 checks; `selftest.py --only l1l2_fixtures` PASS; claims_check/todo_check OK.

- [x] **H99 — `.github/workflows/README.md` still documents the pre-H85 hard gate (selftest + claims + todo), not `tools/gate.py`**
  - Status: done · Owner: task/h99-workflows-readme-gate · Critical: no · Pair: solo
  - Depends: H85 (the gate runner, done); H53 for the todo half of the policy text only
  - Goal: the workflow README is the contract a new agent reads, and it names three commands `ci.yml` no longer runs as three steps: `python tools/selftest.py --json`, `python tools/claims_check.py`, `python tools/todo_check.py TODO.md`. The actual gate is one step, `tools/gate.py`, with `claims_check --strict --count-check` and the PASS/FAIL/SKIP policy, and a SKIP that is never PASS. The README also does not say `fn_audit` is the step that SKIPs for the missing head, so a reader cannot tell what CI actually covers.
  - Precheck: `grep -n 'tools/gate.py' .github/workflows/README.md` prints nothing; `sed -n '7,14p' .github/workflows/README.md` lists the three old commands.
  - Scope: `.github/workflows/README.md` only (H86 owns the `l1l2-fixtures.yml` policy text and the negative-CI proof — do not duplicate it). Rewrite the "Hard gate" list to the one `tools/gate.py` step, name the four gates and the SKIP rule, and add one line that `fn_audit` is SKIP in PR CI (no head) and PASS in H84's manual job. Keep the Python 3.14 informational paragraph.
  - Input: `.github/workflows/{README.md,ci.yml}`, `tools/gate.py` docstring, H85/H86 blocks.
  - Hints: keep it short — one gate row per command, matching `gate.py`'s table (`selftest`, `claims_check`, `todo_check`, `fn_audit`). H86 is still open and edits the same file's policy wording; if H86 lands first, this task is the narrower "name gate.py" fix and must not revert H86's text.
  - Done when: `grep -n 'tools/gate.py' .github/workflows/README.md` prints the gate step; the old three-command list is gone; a reader can tell SKIP≠PASS and which gate SKIPs in CI; `python3 tools/todo_check.py` OK.
  - Stop: if H86's rewrite already names `tools/gate.py`, close this as superseded by H86 with a one-line `Result:` and keep the H86 task.
  - Falsifier: `README.md` still tells an agent that `ci.yml` runs `selftest.py --json` and `claims_check.py` as separate hard-gate steps.
  - Claims: C-4270–C-4279
  - Result: EXP-2026-11-21-H99-workflows-readme. `.github/workflows/README.md`'s "Hard gate" list is now the one `python tools/gate.py` step with a four-row table matching `gate.py`'s `Gate(...)` names (`selftest`, `claims_check --strict --count-check`, `todo_check`, `fn_audit`), the SKIP-is-never-PASS rule, and the line that `fn_audit` SKIPs in PR CI but must PASS in H84's manual job; the pre-H85 three-command list is gone (`grep` of it exits 1). `tools/gate.py` line 30, old three-command list line 30–32 gone. No workflow logic changed. `python3 tools/todo_check.py` OK (0 errors, 156 warnings), `claims_check --strict --count-check` OK, `python3 tools/gate.py` `4 pass, 0 fail, 0 skip`. Claims C-4270–C-4274.

- [x] **H100 — `claims.md` carries 285 `RESERVED (TASK).` placeholder rows, and no gate notices when the task is `done`**
  - Status: done · Owner: task/h100-claims-reserved · Critical: no · Pair: required
  - Depends: — (claims_check is on `main`); the retro 2026-11-17-3 multiplicity finding
  - Goal: a 10-ID block was meant to be a reservation, but every block was also written out as ten `| C-xxxx | RESERVED (TASK). | — | — | — |` rows, and nothing ever removes them. SE 2026-11-17 counted **285 RESERVED rows over 60 tasks**: **97 rows name a `done` task** (e.g. C-4179 for the just-merged M9.39, C-4139 for H90, C-4102…C-4109 for H87), 34 name a `blocked` task, and 151 name a task no longer in TODO.md. `claims_check --strict --count-check` passes over all of them, so "reserved" reads as "registered" (the retro's exact defect) and an agent scanning for the next free claim sees a wall of dead placeholders. Make the placeholder a gate-visible state and retire the rows whose owner is `done`.
  - Precheck: `grep -c 'RESERVED (' docs/research/claims.md` prints `285`; `grep -o 'RESERVED ([A-Za-z0-9._]*)' docs/research/claims.md | sort | uniq -c | sort -rn | head` shows the per-task spread; `python3 tools/claims_check.py --strict --count-check` is OK with those rows present (the defect: no gate sees them).
  - Scope: `tools/claims_check.py` (a `--reserved` mode, on under `--strict`) that fails when a `RESERVED (<ID>).` row names a task whose `Status:` is `done` or that is absent from TODO.md, with the task ID and count in the message; and `docs/research/claims.md` — delete the RESERVED rows for `done`/absent tasks (keep the rows for `open`/`in progress` tasks, which are true reservations). Do **not** renumber any real claim ID and do not touch a task's numeric `Claims:` header. If a whole block's owner is gone but its numbers must stay scar-free, leave a single `| C-a–C-b | reserved block, owner retired |` note row rather than ten.
  - Input: `tools/claims_check.py` (`_run_counts`, `main`, the row parser), `docs/research/claims.md`, the TODO `Status:` values (`todo_check._parse_status`), the 285-row census above.
  - Hints: match the owner token exactly (`RESERVED \(([^)]+)\)`); a `done (negative …)` status still parses as `done` via `_parse_status` so H95-style blocks retire too. Keep the check additive (default off is wrong here — the retro wants it loud), but make the message list at most ten offending tasks so it stays readable. The 151 absent-task rows are the bulk; deleting them must not change `--count-check`'s mismatch count (those are not count-bearing rows).
  - Done when: `python3 tools/claims_check.py --strict` fails on today's `claims.md` with a `RESERVED row names done/absent task` list; after the cleanup it passes and `grep -c 'RESERVED (' docs/research/claims.md` counts only rows whose owner is `open`/`in progress`; a synthetic fixture with one done-owner RESERVED row fails and one open-owner row passes (`--selftest`); `python3 tools/gate.py` green; `--count-check` still `0` mismatches.
  - Stop: if deleting the absent-task rows would break a `Supersedes:`/`Superseded by:` pointer, keep those specific rows and list them as `OBSERVED retained` — never renumber a real claim.
  - Falsifier: a `RESERVED (M9.39).` row (M9.39 is `done`) still passes `--strict` after the change.
  - Claims: C-6380–C-6383
  - Result: done (owner renumber round). `tools/claims_check.py --reserved` (on under `--strict`) fails on a bare `RESERVED (owner).` row whose owner is `done`/absent; the 288 dead rows were deleted and the two `M9.36`-owned placeholders (C-3588/C-3589, whose M9.36 block is done) retired, leaving 38 live placeholder rows. The four H100 claims were renumbered C-5810–C-5813 → C-5970–C-5973 (M3.11b collision) → C-6290–C-6293 (M9.17 collision) → **C-6380–C-6383** (M1.36b claimed C-6290–C-6299 on `main`). Rebased onto `origin/main`; `claims_check --strict` `0 rows over 0`, `--count-check` 0 mismatches. EXP: EXP-2026-11-20-H100-claims-reserved.

- [x] **H62 — `fetch_image.py`: a `US256` head alias pinned to `70d945d8…`, so rule 11 holds for US tasks**
  - Status: done · Owner: task/h62-us256-alias · Critical: no · Pair: solo
  - Depends: — (`tools/fetch_image.py` is on `main`; `--part 256M` exists)
  - Goal: the EU head is a pinned first-class key (`IMG256`, `92aa525d…`), but the US head every US task needs is cited four times (`M1.22`, `M1.22b`, `M1.28` block/Result) as `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img` with the hash `70d945d8…` in prose. `fetch_image.py --image US --part 256M` verifies size only ("no SHA-256 pinned"), so a truncated/overwritten local card is not caught and no command is re-runnable from a clean checkout (rule 11).
  - Precheck: `python3 tools/fetch_image.py --image US --part 256M -o /tmp/opencode/x.img` prints `size verified; no SHA-256 pinned`; `python3 tools/fetch_image.py --image US256 -o /tmp/opencode/x.img` exits `2` `unknown image 'US256'`; `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img | sha256sum` is `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da` and is byte-identical to `/tmp/opencode/us256.img`.
  - Scope: `tools/fetch_image.py` only: `PART_PINS[("US", "256M")] = (256 MiB, 70d945d8…)` and `ALIASES["US256"] = ("US", "256M")`; `--list` shows it; extend the `--selftest` so `resolve("US256", None)` returns the pinned hash and `resolve("US256", "1G")` exits 2. Not: changing any full-image pin, the EU head, or an EXP.
  - Input: `tools/fetch_image.py` (`IMAGES`, `PART_PINS`, `ALIASES`, `resolve`, `selftest`), the US SHA-256 above, `TODO.md` "Shared inputs" table.
  - Hints: the `IMG256` alias is the template — one `PART_PINS` entry plus one `ALIASES` line; the fixture already pins the same hash (`tools/fixtures/fn_match_eu_us_2011.json` `us_head`), so the two must agree (add a selftest check that they do, reading the fixture JSON).
  - Done when: `python3 tools/fetch_image.py --image US256 -o /tmp/opencode/us256-new.img` verifies `70d945d8…` (or `--verify` names it); `--image US --part 256M` now also verifies the hash; `python3 tools/selftest.py --only fetch_image` passes with the new cases; the `Shared inputs` table gains a `US256` row.
  - Stop: if the upstream US image is re-released (hash differs), record the new full-image hash in an EXP and pin the new head; never pin a hash you cannot reproduce from the card.
  - Claims: C-3820–C-3829
  - Result: [EXP-2026-11-19-H62-us256-alias](docs/experiments/EXP-2026-11-19-H62-us256-alias.md) — `--image US256` downloads the real US head in 27 s and verifies `70d945d8…` (`cmp`-identical to `archive/us256.img`); `--image US --part 256M` now verifies the same hash; EU head, a 1-byte flip and a 1-byte-short copy are refused (exit 1); selftest +5 checks incl. fixture agreement (C-3820–C-3823).

- [x] **H63 — `fn_audit`: a `CORRECTED` verdict must name the line-specific evidence that resolved it**
  - Status: done · Owner: task/h63-corrected-evidence · Critical: no · Pair: required
  - Depends: — (`tools/fn_audit.py`, M1.29 on `main`); coordinates H52 (edits the citations) and M1.26 (reuses the verdict)
  - Goal: `CORRECTED` is a success class, so its evidence must be visible on the row. Today an `INSIDE` becomes `CORRECTED` either because the *same line* pairs the VA with its true start or because the VA is on the static `CORRECTION_ONLY` pin; the printed row says only `CORRECTED 0x…`. The pin is a fleet-wide allowlist, so a bare `… are mid-function` line is resolved by the pin even though the line names no start. On the frozen `b56fed2` corpus the example is `TODO.md:714` (the M1.25 Goal lists the three H51 VAs as mid-function, no pair, no start): dropping the `0x00542256` pin alone turns that line's third VA into `INSIDE` — `INSIDE` 33→36, `CORRECTED` 13→10. **Post-H52 (2026-11-16) the same defect survives but smaller:** on `main` at `26f33cd` `--scope docs` is `START 229, INSIDE 0, CORRECTED 25`, and popping the same pin gives `INSIDE 5, CORRECTED 20`; the pinned VA stays `CORRECTED(pin)` on a line where the other two H51 VAs are `INSIDE` (H52 left them as historical co-citations), so the pin hides which VA the line actually resolved.
  - Precheck: on the `b56fed2` worktree (`git worktree add --detach /tmp/opencode/h63wt b56fed2`, then run `tools/fn_audit.py <abs>/archive/head256.img --scope docs --quiet` from it) the summary is `START 190, INSIDE 33, CORRECTED 13, GAP 29`; popping the `0x00542256` pin gives `INSIDE 36, CORRECTED 10`. On `main` at `26f33cd` the same command is `START 229, INSIDE 0, CORRECTED 25`; popping the pin gives `INSIDE 5, CORRECTED 20` (measured 2026-11-16) — the split must be exported on `b56fed2` as the stable corpus and only *re-measured* on `main`, never re-pinned to freeze a number. The pinned VA's line shows it as `CORRECTED` while the other H51 VAs on that line are `INSIDE` — one pin resolved a line that names no start.
  - Scope: `tools/fn_audit.py` only: a fourth label token, `CORRECTED(line)` vs `CORRECTED(pin)`, and a summary line `CORRECTED <n> (<line> line, <pin> pin)`; the pin path keeps its own selftest and `--verbose` keeps printing the allowlist. Not: changing a citation (H52), re-pinning to freeze a number, or counting the live board as if it were fixed.
  - Input: `tools/fn_audit.py` (`Verdict.label`, `_resolved`, `report`, `CORRECTION_ONLY`), EXP-2026-11-15-M1.29-fn-audit-corrections §Observations (the 13-row table and the 6+3+2+1+1 split), the `b56fed2` worktree (the only corpus whose 33/13 is stable).
  - Hints: `_resolved` already knows which branch fired — pass the branch into the verdict instead of re-deriving it in `label()`; keep `is_failure` and `--fix-list` untouched (neither may start printing a `CORRECTED` row). The number for the EXP is *which citations are pin-resolved*: run it on `b56fed2` so it does not move under later board edits. If a pin-resolved citation's own line pairs a different start, that is a second defect — report it, do not auto-fix. Each pin the EXP keeps must carry a `Pin:` line naming its independent re-check: `0x00542256` → M1.24's `--parent-of`; `0x003f5fc2`/`0x00413af4` → `pdata.py fn` at the call site. A pin with no such line is a candidate for H52 instead. Because the count moves with the board, M1.26's gate must run on a frozen corpus (a committed JSON snapshot, M1.30), never live `TODO.md`.
  - Done when: on `b56fed2` the split prints `CORRECTED 13 (<line> line, <pin> pin)` with the arithmetic in the EXP and the live tree's larger `CORRECTED` measured in the same EXP (same `INSIDE`, so the difference is only the added prose); every pin the EXP keeps has a `Pin:` line whose re-check command runs; `--selftest` proves a pair-resolved citation is labelled `line` and a pin-resolved one `pin`; with the `0x00542256` pin removed on `b56fed2` the summary reads `INSIDE 36, CORRECTED 10`; `selftest.py --only fn_audit` and `claims_check.py` pass.
  - Stop: if the split cannot be exported without changing the 13/33 counts, record the counts as an OBSERVED claim and ship only the label; do not redefine `CORRECTED`.
  - Claims: C-3830–C-3839
  - Result: EXP-2026-11-20-H63-corrected-evidence; C-3830–C-3836 (C-3837–C-3839 reserved). Rows print `CORRECTED(line)`/`CORRECTED(pin)` and a `fn_audit: CORRECTED <n> (<line> line, <pin> pin)` line; on `b56fed2` **`CORRECTED 13 (5 line, 8 pin)`** with `INSIDE 33` unchanged, `--drop-pin 0x00542256` → `INSIDE 36, CORRECTED 10`; live tree `CORRECTED 20 (12 line, 8 pin)`, `INSIDE 0`; 0 second defects; all three pins kept with `Pin:` re-checks (`sh4dis`/`pdata.py fn`; M1.24 `--parent-of` once merged).

- [x] **H65 — `progress_report`: its L4 prerequisite names an ID that is no longer a block**
  - Status: done · Owner: task/h65-progress-l4-prereq · Critical: no · Pair: solo
  - Depends: — (`tools/progress_report.py` is on `main`); coordinates H60 (the same live/archived/ghost distinction, for one hard-coded ID)
  - Goal: every default `progress_report.py` run prints `Parse/input problems — TODO.md: task M8.A1 not found`, because `L4_PREREQ` hard-codes `M8.A1` while `M8.A2`'s block now says `Depends: — (M8.A1, M8.A4 and M8.A5 are merged)` and the block is gone. The dashboard therefore cannot show a checked L4 prerequisite, and a reader cannot tell "missing from this TODO" from "this TODO is broken". QA 2026-11-16 hit it on the first post-#171 run.
  - Precheck: `python3 tools/progress_report.py | grep -n 'M8.A1'` prints the problem line and `prereq 'M8.A1': checked=None · None`; `grep -c '\*\*M8.A1' TODO.md` prints 0.
  - Scope: `tools/progress_report.py` only, `L4_PREREQ` and the problem text: resolve a prerequisite ID the way a block is named (merged/archived note in the dependent block, or the history files H60 will classify) and either point at the live stand-in or print `archived` instead of `task not found`; same for any other `*_PREREQ` entry that names no block. Not: adding M8.A1 back to the board, editing M8.* blocks, or changing the layer verdicts.
  - Input: `tools/progress_report.py` (`L4_PREREQ`, `_build_manual_layer`, the `problems` collector), TODO `M8.A2` block, `docs/research/todo-history-2026-11-*.md`.
  - Done when: `python3 tools/progress_report.py` exits 0 and prints no `task M8.A1 not found`; the L4 prerequisite line names a live block or says `archived`; `--selftest` (or the synthetic fixture the tool already uses) covers one missing-prereq case; `selftest.py --only progress_report` passes.
  - Stop: if `progress_report.py` has no fixture mechanism, add only the resolution + a `--json` assertion in `--selftest`, and record in the EXP that H60 will take over the general case; do not fork a TODO parser.
  - Claims: C-3850–C-3859
  - Result: [EXP-2026-11-19-H65-progress-l4-prereq](docs/experiments/EXP-2026-11-19-H65-progress-l4-prereq.md) — an ID with no board block is looked up in `docs/research/todo-history-*.md` (newest first); the default run now prints `prereq M8.A1: checked=True · archived (done) in todo-history-2026-11-09.md:1375` with 0 problems (was `task M8.A1 not found`); an ID in no file or archived `[ ]` stays a problem; selftest +10 checks (C-3850–C-3853).

- [x] **H60 — `todo_check`: a `Depends`/`Unblock` ID must resolve to a live block or an archived one in `todo-history-*.md`**
  - Status: done · Owner: task/h60-todo-depends-resolution · Critical: no · Pair: solo
  - Depends: — (`tools/todo_check.py` is on `main`); coordinates H53 (owns `--strict`)
  - Goal: the PO archive pass (2026-11-15, 21 blocks) is a manual fixpoint run by a script, and its only guard was "all 21 present exactly once" after it had already dropped the H blocks from the history file. Board hygiene still cannot tell a *ghost* ID from an *archived* one: `todo_check.py` reports both as `Depends references unknown task ID`. On the current board that is 16 warnings (H24, H26 ×3, M9, M1.12, M1.2b/c, M3.1, M4.5, M4.7 ×2, M4.8c, M9.1, M9.3/M9.4) and a fresh archive can add more without any gate noticing.
  - Precheck: `python3 tools/todo_check.py | grep -c 'references unknown task ID'` prints `16`; `git ls-files docs/research/todo-history-*.md` is non-empty, so an archive exists to resolve against; `python3 tools/todo_check.py --strict` still exits `2` (H53 owns the flag — this task must not add a second one).
  - Scope: `tools/todo_check.py` only: build a `history_ids` set from `[x]` block headers in `docs/research/todo-history-*.md` (reuse the existing block regex, do not write a second parser) and split the current single warning into (a) `Depends/Unblock references archived task ID 'X'` — informational, resolves to a done block, (b) `… references ghost task ID 'X'` — an error under H53's `--strict`, a warning by default, (c) `… references blocked task ID 'X'`. Add a `--selftest` with a temp board plus a temp history: an archived ref warns, a ghost ref fails under `--strict`, a live ref is silent, and a history file that repeats an ID exactly once stays clean. Do not change the default exit code (0 on the current board).
  - Input: `tools/todo_check.py` (`check()`, `_parse_depends`, `known_ids`), `docs/research/todo-history-2026-11-15.md` (the archive format the PO wrote), TODO rules 9/15 and H53's `--strict` note.
  - Hints: `H53` decides which warnings become errors; this task only makes the three cases distinguishable. Resolve `M8.C1…C22`-style range IDs to their base (`M8.C`) the way the block headers do, or they flood the report. If a history file is absent (fresh checkout), degrade to today's single warning, never to an error.
  - Done when: `python3 tools/todo_check.py` still exits 0 and prints the archived/ghost/blocked split with counts; the selftest's ghost fixture exits 1 under whatever flag H53 lands (or under `--selftest` if H53 is not merged); a temp copy of `TODO.md` with one archived ID changed to `H99` is reported as ghost; `selftest.py --only todo_check` passes.
  - Stop: if H53's `--strict` shape differs from the plan above, implement the classification as warnings only and record in the EXP which rule H53 must pick up; do not fork a second TODO checker.
  - Result: `docs/experiments/EXP-2026-11-20-H60-depends-resolution.md` (C-3800–C-3809). `tools/todo_check.py` reads the `[x]` headers of every `docs/research/todo-history-*.md` and splits each unresolved `Depends`/`Unblock` reference into `archived` (informational), `ghost` (nowhere) and `blocked` (a live blocked block); the summary prints `refs archived 42 / ghost 0 / blocked 27 (174 archived IDs)` on the board at `434a2949`. With no archive a reference degrades to the old `unknown task ID` wording and still exits 0. The split exposed one real ghost — H43's `Depends: … M9 …` (a stream, not a task), now the five `M9.x` reader targets. Default exit stays 0 and `--strict`'s verdict set is untouched (its remaining 9 `ERROR` lines are H53's firmware fields); `--selftest` 18→24 checks; `gate: 4 pass, 0 fail, 0 skip`.
  - Claims: C-3800–C-3809

- [x] **H76 — `selftest.py` pins `L3 OVERLAY: 0 moved`, so any TODO edit reddens the full suite (H69's exact-string residual)**
  - Status: done · Owner: task/h76-l3-image-assert · Critical: no · Pair: solo
  - Depends: H69 (done: moved-only is a warning, exit 0), M1.26 (done: the `fn_audit_l3_image` suite this fixes)
  - Goal: `test_fn_audit_scope_l3_image` asserts the literal string `CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved`, but H69's policy says a moved-only identity set is a `CORPUS DRIFT` warning with **exit 0**; H74's TODO edit moved 51 l3 lines, so `main` prints `CORPUS DRIFT: … 0 new / 0 gone / 51 moved` and the full `selftest.py` is RED (`passed=89 failed=1`). This is the same brittle exact-string class H69 removed for the gate's pass/fail; fix the test, not the corpus.
  - Precheck: `python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json --quiet` prints `CORPUS DRIFT: L3 OVERLAY: 0 new / 0 gone / 51 moved` and exits 0; `python3 tools/selftest.py` is RED on `fn_audit_l3_image` (AssertionError on the literal).
  - Scope: `tools/selftest.py` only — `test_fn_audit_scope_l3_image` accepts `CORPUS (OK|DRIFT): L3 OVERLAY: 0 new / 0 gone / N moved` and rejects any `CORPUS STALE`/non-zero exit, so a moved-only run is a pass and a real `new`/`gone` still fails (exit 1 already asserted). Add `import re`. Not: refreshing the overlay, editing `fn_audit.py`'s policy, or touching the docs base.
  - Input: `tools/selftest.py` `test_fn_audit_scope_l3_image`; `docs/experiments/EXP-2026-11-16-H69-snapshot-refresh.md` (the policy); `tools/README.md` `--scope l3` (moved-only warns, exits 0).
  - Hints: the old test was written when the tree happened to be byte-stable; the H69 policy forbids pinning `0 moved`. Keep the negative control (`fn_audit_l3` without the image already proves a new `INSIDE` fails).
  - Done when: `python3 tools/selftest.py` is green (`failed=0`); a synthetic overlay with one row deleted (`1 new / 0 gone`) makes the same gate print `CORPUS STALE` and exit 1 (the negative control the relaxed assertion must still let through); `python3 tools/selftest.py --only fn_audit` still passes.
  - Result: EXP-2026-11-16-H76-l3-image-assert; C-3990–C-3999. `test_fn_audit_scope_l3_image` accepts `CORPUS (OK|DRIFT): L3 OVERLAY: 0 new / 0 gone / N moved` and asserts no `CORPUS STALE`; full `selftest.py` 90/0/23, and a one-row-deleted overlay still yields `CORPUS STALE: … 1 new / 0 gone` exit 1.
  - Claims: C-3990–C-3999

- [x] **H85 — One standing gate runner: `selftest` + `claims_check --strict/--count-check` + `todo_check` + the l3 corpus gate in one command**
  - Status: done · Owner: task/h85-standing-gate · Critical: yes · Pair: required
  - Depends: H78 (makes `--strict` run the count rule, so the runner must not cherry-pick flags), H76 (the l3 suite's skip semantics), H53 (whose strict errors the runner reports but does not fail on until the board is clean)
  - Goal: the TL/QA gate is four commands with different exit semantics (`selftest.py`, `claims_check.py [--strict] [--count-check]`, `todo_check.py [--strict]`, `fn_audit.py --corpus … --overlay …`), and the cycle-8 escape proves the cost: a pair both ran `selftest.py` in a worktree **without** `archive/head256.img`, where `fn_audit_l3_image` is `skip_unless`, so both saw `passed=89/90` and only the main checkout saw the red l3 suite. `todo_check --strict` is also red (69 errors over 25 tasks) while the default is green, so "which exit code is a failure" is currently a judgement call each agent re-makes. One runner with one policy, one `--json`, and one explicit `SKIP (why)` list removes that judgement.
  - Precheck: the four commands disagree today: `python3 tools/selftest.py` -> `passed=90 failed=0 skipped=23`; `python3 tools/claims_check.py --strict` -> exit 0 **but** `--strict --count-check` -> exit 1 (`COUNT C-3704 …`); `python3 tools/todo_check.py` -> exit 0 and `--strict` -> exit 1 with `69` ERROR lines; `python3 tools/fn_audit.py archive/head256.img --corpus … --overlay … --quiet` -> exit 0, and with the image absent -> exit 2 with a `no image` message.
  - Scope: a new `tools/gate.py` (name in PR) that runs, in a fixed order, `selftest.py --json`, `claims_check.py --strict` (+ `--count-check` once H78 lands; a `--no-count` escape only if `--strict` does not subsume it), `todo_check.py` (default; `--strict` under a `--board-clean` flag or when H53 is done) and `fn_audit.py --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json` (when the image exists). It prints a per-gate `PASS/FAIL/SKIP (reason)` table and a `--json` artifact, exits non-zero when any runnable gate fails, and **exits 0 with `SKIP` only when the gate needs a missing vendor input** — the same contract `realcheck.py`/`selftest.py` already use. Wire it into `ci.yml` (no image → the l3 gate reports `SKIP: no archive/head256.img`) and into H84's manual job (image present → the l3 gate must PASS or the job fails). No change to any tool's rules.
  - Input: `tools/selftest.py` (`--json`, `skip_unless`), `tools/claims_check.py` (`--strict`, `--count-check`), `tools/todo_check.py` (default vs `--strict`), `tools/fn_audit.py` (`--corpus`, `--overlay`, exit 2 = no image), `.github/workflows/ci.yml`, `docs/research/fn-audit-*-2026-11-16.json`, AGENTS.md "Verification ladder".
  - Hints: the runner's own `--selftest` must prove the SKIP distinction with a stub gate (a gate that exits 2/`no image` is SKIP, a gate that exits 1 is FAIL, a gate that exits 0 is PASS) — that is the H76 lesson applied to the aggregator. Do not let the runner turn a SKIP into a pass in the summary line; print both. Keep the TL's per-task `Done when` out of it (the runner is the *standing* gate, not the per-task oracle).
  - Done when: `python3 tools/gate.py` on this host prints a table with `selftest PASS`, `claims_check FAIL` (exit 1 due to C-3704 until H78 lands) — or `PASS` after H78 — `todo_check PASS` (default), `fn_audit SKIP (no image)` **or** `PASS`, and exits non-zero iff a runnable gate failed; `--json` gives the same; `gate.py --selftest` covers PASS/FAIL/SKIP with stubs; `ci.yml` calls it on 3.11/3.13 and its SKIP text is visible in the job summary; `python3 tools/selftest.py` stays green.
  - Stop: if composing the four tools' output shapes into one schema needs a second parser per tool (no shared `--json` contract), ship the sequential runner with a plain-text table and a non-zero exit, and record the schema gap as a follow-up to H27/H42 rather than inventing a fifth format.
  - Result: EXP-2026-11-16-H85-standing-gate; C-4080–C-4089. New `tools/gate.py` runs `selftest.py`, `claims_check.py --strict --count-check`, `todo_check.py` and `fn_audit.py --corpus … --overlay …` in one fixed order with one policy: **PASS**, **FAIL**, or **SKIP (reason)** for a missing vendor input — exit 2 with a missing-input marker is SKIP, exit 2 without one is FAIL, so `fn_audit`'s exit 2 is not blanket-forgiven. No image: `3 pass, 1 skip` (`fn_audit SKIP …`), exit 0; with the image: `4 pass, 0 fail, 0 skip`, exit 0 (H78 made the strict count gate green). A genuine failure (a block's `Status:` removed) is `FAIL` + exit 1. `--json` (file or `-`), `--board-clean` (todo_check --strict, red until H53) and `--no-count` are supported; `--selftest` proves all three outcomes with stubs (11 checks, python 3.11/3.13/3.15), including that a `cannot verify` exit-2 is FAIL. `ci.yml` collapses three gate steps into one and writes the SKIP list to the job summary; `selftest.py` stays `passed=90 skipped=24` with `tool:gate PASS`.
  - Claims: C-4080–C-4089

- [x] **H89 — The 1,259 unexplained `fn_match` NOMATCH are the next census: rewrites or a second matcher class**
  - Status: done · Owner: task/h89-nomatch-census · Critical: no · Pair: required
  - Depends: M1.22b (which classified the 13 cited readers and left 1,259 unexplained)
  - Goal: after M1.22b the module census is `UNIQUE 2392 / DIFFERENT 3214 / CALLORDER 213 / AMBIGUOUS 518 / NOMATCH 1259` (total 7596). The 1,259 are unexplained: each has no hash hit, no unique masked-form twin and no call-order match. Decide per sample whether they are real rewrites (a differing instruction) or a second matcher class (e.g. reordered basic blocks, a different register allocation with the same semantics, a function split/merge), so a future leaf/reader task knows whether the US code is missing or the matcher is.
  - Precheck: `python3 - <<'EOF'` (the M1.22b census script) prints `NOMATCH 1259`; `python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va <one unexplained VA> --json /tmp/x.json` carries `diff: null` and `verdict: NOMATCH`.
  - Scope: a sampling study, not a matcher change: pick a counted random sample of the 1,259 (state the seed and size), classify each by disassembly (same opcode stream with a reordered block / different register allocation / genuinely different), and publish the distribution with the first differing instruction per sampled function. `tools/fn_match.py` changes only if the study finds one class that is cheap and safe to add (and then it is a separate task).
  - Input: `tools/fn_match.py` (`_pool_only_twin`, `code_digest`, `leaf_compare`), `tools/sh4dis.py`, the M1.22b EXP and C-3626.
  - Hints: this is the same shape as M1.22b, one level down — do not start from a matcher idea, start from disassembly of a handful and let the classes fall out. A sample of 30–50 is enough to size the classes; a full 1,259 classification is not the goal.
  - Done when: an EXP reports the sampled distribution with counts and the first differing instruction per class, and says whether the 1,259 are mostly rewrites or a matcher class; a claim names the dominant class and its evidence; `python3 tools/gate.py` green.
  - Stop: if the sample is all one class with no cheap fix, record it and do not change `fn_match.py`.
  - Result: docs/experiments/EXP-2026-11-20-H89-nomatch-census.md; C-4120–C-4126. New tool `tools/nomatch_census.py` pairs each NOMATCH by address order (no matcher hash; anchor control 38/40 UNIQUE re-paired; classifier control 0/40 wrong neighbours classed same code; pipeline controls: shifted anchors without fallback keep 73 of 360 same-code rows, shuffled 1). Sample seed 89, 40 of 1259: `TWIN 13  PHANTOM-SLOT 3  IMMEDIATE 4  EDIT 7  REWRITE 5  UNPAIRED 8` — 16 identical code, 24 real differences or no counterpart; no function differs only in register allocation or only in order (`REGALLOC`/`REORDER` 0). Population (tool only): same code 360/1259. Mostly rewrites, but the largest single class is a matcher class: `TWIN` (identical stream shared by ≥2 US functions). Two cheap fixes filed as H113 (forward-pass pool slots, 141 functions) and H114 (address-order pick among twins, 219 rows; must be one-to-one); `fn_match.py` unchanged. Navigator round 1 corrections are in the EXP.
  - Claims: C-4120–C-4129

- [x] **H93 — H90's EXP still has an empty "Corrections after navigator review" section**
  - Status: done · Owner: task/h93-h90-corrections-2 · Critical: no · Pair: required
  - Depends: H90 (the EXP it repairs is on `main`)
  - Goal: H90 was `Pair: required` and the navigator round happened (TL log `2026-11-17-0859-42-tl.log`, commit `4e7ea5d`), but `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` still ends with `## Corrections after navigator review` and `(empty until the navigator round returns)`. A reader cannot tell the record was paired, and an empty placeholder looks filled — the defect class `prompt_tl.txt` now names.
  - Precheck: `grep -A1 'Corrections after navigator review' docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` prints the `(empty until …)` line.
  - Scope: `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` only: write the two navigator corrections the TL log records — "12 consecutive pushes" pinned to `1889340`…`2b3d1b4` (last green `3f9c0b2`), and the depth-1 recipe pinned to the pre-fix tool revision — or, if the round cannot be shown, delete the heading. No claim rows; no other EXP.
  - Input: the H90 EXP, TL log `2026-11-17-0859-42-tl.log` ("navigator round 1: APPROVE, with two non-blocking number flags"), `4e7ea5d`.
  - Hints: the two flags are already in the TL log; quote them, do not invent a third. If a quote would duplicate the Result line, point at it instead — the section is about the round, not the fix.
  - Done when: no `(empty until the navigator round returns)` remains in the H90 EXP; the section names two corrections or the heading is gone; `python3 tools/claims_check.py --strict --count-check` OK; `python3 tools/todo_check.py` OK.
  - Stop: if the TL log's two flags cannot be quoted without a vendor byte or a typed number, delete the heading and record why in the EXP, then stop.
  - Falsifier: the empty-placeholder grep still prints after the edit.
  - Claims: C-4190–C-4199
  - Result: `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` § Corrections after navigator review now quotes the TL log's two flags and where `4e7ea5d` applied each: (1) 12 consecutive red pushes `1889340`…`2b3d1b4`, last green `3f9c0b2` (Question, Inputs, Interpretation, C-4130, H90 Goal); (2) the depth-1 recipe pinned to the pre-fix tree. `4e7ea5d` had pinned only C-4131, so the Reproduction block is corrected in place to a depth-1 fetch of `3d79bcc`. Re-run 2026-11-20: shallow (1 commit) `count mismatches: 9`, exit 1; `--unshallow` (809 commits) `0`, exit 0. The placeholder is gone; no claim rows (C-4190–C-4199 unused). The Method's "five `main` pushes" line and the step-2 clone stay for H94.

- [x] **M1.21 — Decode the compressed `FILESentry` payloads with the kernel routine (re-opens M1.3/M1.4)**
  - Status: done · Owner: task/m1.21-filesentry-decode · Critical: no
  - Result: `nk_decomp.py files` (kernel `DECOMP_SECT`, section frame, no file-specific header) decodes every compressed `FILESentry`: build B 8/8 and build C 7/7 on EU2011 and US2011 (`r0 == rsize`; `ceconfig.h` text, `celog.dll` MZ, three `EKIM` hives); build A has one stored file and none compressed; a 1- or 3-byte shifted payload fails. `tools/cehive.py` parses the hives (0 dangling links). `docs/research/rom-registry.md`: main SD slot = `SDHC.dll` port 0 → `SDProfile` → `\SystemSD`; `Navi.exe` is not in the registry — `init` starts `device.exe`/`gwes.exe`, which loads `AppLaunch.dll` (`Drivers\BuiltIn\AppLch`) whose compiled-in table names `\windows\Navi.exe`. M1.4 re-opened (rule 15); follow-up **M1.34**. EXP: `docs/experiments/EXP-2026-11-19-M1.21-filesentry-decode.md`. Claims C-3520–C-3527.
  - Depends: — (H51)
  - Goal: read the ROM *files* of builds A/B/C (registry hives, `.lnk`, `initflashfiles.dat`, bitmaps, text), which M1.4 could not extract. They tell which drivers and paths the unit uses for the SD card and the map (`\SystemSD\…`), and M8 needs the registry.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 files | head` lists `FILESentry` rows with `nRealFileSize` ≠ `nCompFileSize`.
  - Scope: all `FILESentry` rows of A, B, C on IMG256; extraction to `archive/work/` only. Report names, sizes, SHA-256 and file type — no content in the repo except short ASCII keys that are not vendor data (registry key *names* relevant to SD/map paths are fine; values that are vendor strings are quoted by offset).
  - Input: `tools/nk_decomp.py decompress(data, off, comp_size, real_size)`; EXP-2026-11-06-M1.4 (which rows, what failed); EXP-2026-11-05-M1.2a / -M1.2d (the 22/25-byte section header forms — a file payload may start with a different header or none).
  - Hints: try first exactly as for a section (`skip=0, step=1, block=0x1000`). If `r0 = -1`, read the caller of the file path: `sh4xref.py IMG256 nk.exe --image-start 0x3e00200 --to 0x88037590` (`DECOMP_WRAP`) lists every caller; the one that is not the section loader `0x880385e4` is the file reader and shows the arguments it passes (a per-page call with `skip = page*0x1000` is the usual shape). Positive control: a file whose type has a magic (`BM`, `regf`, UTF-16 text, `MZ`).
  - Done when: the EXP lists every `FILESentry` with `real size / decoded length / sha256 / magic`, at least one file per build decodes to a recognisable type, and a short `docs/research/` note names the registry keys that mention `SystemSD`, the SD driver and the Navi launch.
  - Stop: if no argument set decodes a file with a known magic, write the caller's argument trace and stop.
  - Claims: C-3520–C-3527 (C-3528–C-3529 handed to M1.34)

- [x] **M1.22 — The US firmware build: module census and EU→US function map**
  - Status: done · Owner: task/m1.22-us-census · Critical: yes · Pair: required
  - Note (PO re-open): the `Blocker (SE 2026-11-13)` below is historical — M1.22b cleared it; the residual scope is in the Re-opened line.
  - Blocker (SE 2026-11-13): `fn_match.py --selftest` passes and the EU-vs-EU control maps 13/13 UNIQUE, but the EU→US run maps only 5/13 cited readers UNIQUE (`0x0041c7dc→0x00444540`, `0x0041c990→0x004446f4`, `0x0041c044→0x00443da8`, `0x003f632c→0x0041ec8c`, `0x00542250→0x0056454c`); 8 NOMATCH, including the POINT walker leaf `0x003f5194`. That is <90 %, there is no census EXP, and `targets.json` has no `build` field.
  - Re-opened (PO, rule 15): M1.22b merged (PR #203) and supplied the matcher, the census and `build`; the `M1.22b` Unblock condition is met. What M1.22b left undone here: the two US-only modules are **not named** (its census is module-internal), the 13-reader table is `5 UNIQUE / 7 DIFFERENT / 1 NOMATCH` (the ≥90 % UNIQUE floor is not met — M1.22b argued it is a data-layout metric), and the `point_walk_l3.py`/`chunk_decoder_l3.py` reruns with the US VAs (M9.10/M9.12) have not run. Precheck: `python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va 0x003f5194 …` still prints `unique: 5`; `grep -c "US-only\|only on the US" docs/experiments/EXP-2026-11-16-M1.22b-eu-us-census.md` prints `0`.
  - Depends: — (M1.20 makes the matching exact; a first census needs only `cerom.py`)
  - Goal: Marek's unit is a US unit, and the US card carries a **different `Navi.exe`** (H51: vsize `0x013bb000`, entry `0x0035d894`, sec0 `0x56faa6` B, 7,520 function records, 151 modules; EU: `0x0154e000`, `0x0032edd0`, `0x54bd16`, 7,596, 149). Every reader VA on this board was found in the EU build, and the L3 gate for the US cards S1/S2 (M9.10, M9.11, M9.12) runs EU code on US data. Give each located EU function its US address so the gate can run the code the US unit runs.
  - Precheck: `curl -r 0-268435455 -o US256.img https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img` (SHA-256 `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da`); `python3 tools/cerom.py --image-start 0x200200 US256.img sections Navi.exe` shows entry `0035d894`; bytes `0x3e00200…0x4800200` (build B) equal IMG256.
  - Scope: (1) add `US256` to `tools/fetch_image.py`; (2) module census EU vs US: name, sizes, section hashes, identical / different / only-in-one (two modules exist only on the US card — name them); (3) new `tools/fn_match.py` (`--selftest`): match functions between two builds by a position-independent hash (instruction halfwords with PC-relative displacements and pool *addresses* masked, pool *values* that are not addresses kept, length from pdata), then propagate through call order for the unmatched ones; (4) the EU→US table for every VA in `docs/format/firmware.md`.
  - Input: IMG256 + US256; `nk_decomp.py pdata` for both (the US build decodes with the same routine); `tools/sh4dis.py` for operand classes; the located EU functions: `0x003f5194` (POINT walker, leaf), `0x0041c7dc` (chunk engine) and its callers `0x0041c990`/`0x0041c044`, `0x0041a438` (MMAIN), `0x00419350` (DRSTR), `0x004125a8`/`0x003fbed8`/`0x0040b358` (REFER access path), `0x003bc960` (RDSTM), `0x003f632c`/`0x003f61bc` (name accessor chain), zlib `0x00542250`.
  - Hints: the US build is "larger code, smaller BSS", so nothing is at the same address; do not try a constant offset. Strings help as anchors: the same literal (`LCTBL001.DAT`, `\SystemSD\REFER001\`, zlib messages) has one loader in each build. The map-reader DLLs may be byte-identical between the builds even where `Navi.exe` is not — the census answers that first and may make most of the port trivial. The US card has `XMD` instead of `TMC` and `INDEX001.DAT` (M3.12), so expect real code differences in the REFER path.
  - Done when: the census table is in an EXP; `fn_match.py` maps ≥ 90 % of the EU functions listed above with a unique match (the rest named with the reason); `point_walk_l3.py walk` and `chunk_decoder_l3.py run` are re-run **on US256 with the US VAs** on the US `POINT010` page and give the same result as the EU-code runs; `targets.json` gains a `build` field (`eu2011` / `us2011`), and M9.10/M9.12 name the US build as the gate for S1/S2.
  - Stop: if fewer than half of the functions match uniquely, publish the census and the anchors found, and block on M1.20/M3.23.
  - Result: EXP-2026-11-17-M1.22-us-build-census; C-3530–C-3539, C-3630–C-3639. Census: 149 EU / 151 US modules, US-only `RBDS_CC.dll`, `XMCC.dll`, `XMStatusCC.dll` (three, not two), EU-only `RDSCC.dll`, and exactly one code-identical module (`atlce400.dll`) of 148 common. The `>= 90 % UNIQUE` floor is **not met and measures data layout**: 5 exact + 7 same-form/different-literal + 1 genuinely rewritten reader (the rewrite diverges at halfword 11, so the matcher can still fail). The POINT walkers and the chunk engine now run on US code: new `--build eu2011|us2011` in `point_walk_l3.py` and `chunk_decoder_l3.py`, all US VAs derived from each engine's own literal pool (the dispatcher pool disambiguated the skip walker from the nth reader), page `0x840ba0` 9/9 and byte-identical chunk decode; three wrong-build controls all stop on an unmapped access. `targets.json` gains `cmp_ind_reader_us2011` (+ its `l3check` evidence row), `fn_audit` skips US VAs in the target/const collectors too, and both corpus snapshots are re-pinned (docs base `INSIDE 0`, both layers `0 new / 0 gone`). Honest limitation: the US and EU factory `POINT010` pairs on hand are byte-identical, so this proves the code paths, not a differing page.
  - Claims: C-3530–C-3539

- [x] **M1.32 — Give the M1.22 US reuse points one owner: `targets.json` starts, `point_walk_l3`/`chunk_decoder_l3` tables, the fn_audit skip set, the EXP, the format doc**
  - Status: done · Owner: task/m1.32-us-reuse-owner · Critical: no · Pair: required
  - Depends: M1.22 (done) whose US VAs these are; H91 (fixes the one stale count the copy left behind)
  - Goal: M1.22's three US walker starts and the chunk engine now live in five places that must agree: `tools/l3_harness/targets.json` (`build: us2011`), `tools/point_walk_l3.py` `BUILD_TARGETS["us2011"]`, `tools/chunk_decoder_l3.py` `BUILD_TARGETS["us2011"]`, `tools/fn_audit.py` `US_BUILD_STARTS`, and the prose in `docs/format/firmware.md` + the EXP. That is the M1.28/M1.22b lesson repeated one layer up: a VA set copied by hand into five files is one merge away from disagreeing (H91 already found one symptom), and a new reader adds a sixth copy.
  - Precheck: emit the five sets and diff them:
    `python3 - <<'EOF'` reading `targets.json` (`entry.va` where `build == "us2011"`), both `BUILD_TARGETS["us2011"]` maps and `fn_audit.US_BUILD_STARTS`, printing `only in X: …` per pair. Expected today: the walker/chunk VAs agree, `0x0035D894` (Navi.exe entry) and `0x0041E63C` (dispatcher) appear in some sets only, and the doc table lists a subset — print the counts, do not assert zero before the task decides ownership.
  - Scope: the US-VA declaration only. Decide **one** home (Hints) and make the other files derive or *check* it; `targets.json` stays the machine list the runner reads. No new firmware search, no VA change, no verdict change.
  - Input: `tools/l3_harness/targets.json`, `tools/point_walk_l3.py` `BUILD_TARGETS`, `tools/chunk_decoder_l3.py` `BUILD_TARGETS`, `tools/fn_audit.py` `US_BUILD_STARTS`, `docs/format/firmware.md` §"The US build at L3", EXP-2026-11-17-M1.22-us-build-census.
  - Hints: the natural owner is a small `tools/build_targets.py` (or a `--build us2011` lookup on `targets.json`) that returns `{role: va}` and a `check` mode asserting every hand-written copy equals it; `fn_audit` needs the set at import time, so a generated `dict` in one module is fine. `chunk_decoder_l3`'s helper VAs (memcpy, mod, zcalloc/zcfree, inflate_mask) are not reader starts — keep them out of `US_BUILD_STARTS` (that was the over-broad-skip bug), so the shared set is starts-only and the helpers stay per-tool with a pointer to the pool-slot evidence.
  - Done when: one command prints `0 only-in-*` across the files it owns (or a named, justified exception list with the reason each VA is file-local); `python3 tools/selftest.py --only fn_audit --only point_walk_l3 --only chunk_decoder_l3` passes; `python3 tools/l3check.py --build-corpus` unchanged (`pass=1 blocked=6`); `python3 tools/gate.py` green; the EXP names the owner file.
  - Stop: if a single home needs the runner's JSON schema to grow a second shape the harness cannot read, keep `targets.json` as the home and ship a `check` mode plus one mutation case instead of moving the data.
  - Falsifier: a planted one-halfword drift in one copy is still green after the change.
  - Result: EXP-2026-11-19-M1.32-us-reuse-owner; C-4160–C-4166. Owner is `tools/build_targets.py` (15 roles × EU2011/US2011, kind `start`/`helper`/`data`/`const`): both L3 tools' `BUILD_TARGETS` and `fn_audit.US_BUILD_STARTS` (= `start` roles ∪ fixture US side ∪ entry, still 15) are derived; `build_targets.py check` diffs `targets.json` and the `firmware.md` table and went from `TOTAL only-in-*: 8` (the doc table lacked 8 pairs, code copies already agreed) to `0 across 8 copies`; five planted one-halfword drifts are red in the selftest. The chunk engine still PASSes on both heads with derived VAs; `l3check --build-corpus` `pass=1 blocked=6`; fn_audit's constant scan now reads the owner file (snapshots refreshed, `INSIDE 0`). Exception: the M1.22 EXP (append-only).
  - Claims: C-4160–C-4169

- [x] **M1.31 — Census every `pdata` leaf: `rts` presence and the `0x400` cap, before M1.22b quotes a percentage**
  - Status: done · Owner: task/m1.31-leaf-census · Critical: yes · Pair: required
  - Depends: M1.27 (leaf path + `leaf_window_limit`, done)
  - Goal: M1.27 predicts the 634-leaf census M1.22b will publish, but its own `0x400` cap already truncates one leaf-flagged gap and nothing counts how many **complete** leaves the cap hides. `python3 tools/pdata.py gaps archive/head256.img --module Navi.exe | tail -1` prints `677 gaps > 8 B, 635 leaf`; of those, exactly **one** has a natural bound (next START / called GAP / code end) beyond `0x400` — `0x00558300`, bound 18,966 B, first `rts` at 2,572 B — and `fn_match --va 0x00558300` reports `NOMATCH leaf 1024 B`: a false NOMATCH caused by the cap, not a code difference (whether the `rts` at 2,572 B bounds a function body or data is settled by this task, see Stop). Separately **79** gaps have no `rts` inside their natural bound (true stubs). Neither number is guarded, so a census percentage over "635 leaves" mixes whole leaves, cap-truncated gaps and stubs.
  - Precheck: `python3 tools/fn_match.py match archive/head256.img /tmp/opencode/us256.img --module Navi.exe --va 0x00558300` prints `NOMATCH … leaf 1024 B -> -`; `python3 tools/sh4dis.py archive/head256.img Navi.exe --va 0x00558300 --count 10` decodes it as the start of a real function (the `0x04` value region, not a thunk); a script building `Matcher` and calling `leaf_window_limit(va, starts, called, code_end, limit=1<<20)` vs the default finds exactly one gap where the natural bound > `0x400` and an `rts` lies past `0x400`.
  - Scope: `tools/pdata.py gaps` (record per-leaf `rts_offset` and `natural_bound`) and a new `pdata.py leaves --census` (or a `tools/leaf_census.py` with `--selftest`) that prints, over one real module: total gaps > 8 B, `leaf` flagged, **complete (`rts` inside the natural bound)**, **rts beyond `0x400`** (the cap class, names each VA), **no-`rts` stub** (names counts, not all VAs), and the `0x400`-cap-vs-natural-bound histogram. `fn_match._leaf_verdict` reports `TRUNCATED` (not `NOMATCH`) when the natural bound > the cap and no `rts` was found inside the cap. Not: raising the cap silently (that changes every pairing and belongs to a follow-up with a census proving it is safe), the US census itself (M1.22b), or the 13-VA fixture.
  - Input: `tools/fn_match.py` (`leaf_window_limit`, `leaf_words`, `trim_words`, `_leaf_bound`, `_leaf_verdict`), `tools/pdata.py` (`gaps`, `exec_sections`), `archive/head256.img` (`92aa525d…`).
  - Hints: `trim_words` takes `rts` only inside the already-capped window, so to count "rts beyond the cap" scan the natural bound (`limit=natural`) before trimming — do not just widen the default cap. The one cap case `0x00558300` is the regression fixture (synthetic 0x420-B leaf is cheaper in `--selftest`); a synthetic stub with no `rts` at all must stay `NOMATCH`/stub, not `TRUNCATED`. M1.22b's percentage denominator must be the *complete* count, not `leaf`.
  - Done when: the census prints the four counts for EU `Navi.exe` (measured today: 677 gaps / 635 leaf / 1 cap-truncated `0x00558300` / 79 no-`rts` — the EXP must reproduce or correct these, not re-type them); `fn_match --va 0x00558300` says `TRUNCATED` (or still `NOMATCH` with an explicit `cap=0x400` marker) and the 13-VA fixture still replays `13 rows, 0 mismatch`; `--selftest` covers a synthetic 0x420-B complete leaf (cap-truncated) and a 12-B no-`rts` stub (not truncated); `selftest.py --only fn_match` and `--only pdata` pass; M1.22b's `Depends` gains M1.31.
  - Stop: if the `0x00558300` `rts` at 2,572 B is inside a data jump table rather than a function body (the disassembly shows `0x04`-schema words, so this is plausible), record it as `OBSERVED`, keep `NOMATCH`, and census only the no-`rts` stubs; never raise the cap to "fix" one address.
  - Claims: C-3960–C-3969
  - Result: EXP-2026-11-16-M1.31-leaf-census; C-3960–C-3969. `tools/pdata.py leaves --called {records,gaps,all}` prints the census over every GAP with the call set named: on `archive/head256.img` (`92aa525d…`) `Navi.exe` has 677 GAPs, 635 `leaf`; under `fn_match`'s clamp (`--called records`) `complete 598 (leaf 579)`, `no-rts stub 77 (leaf 54)`, 2 cap rows `0x00558300(rts+2572,bound 0x4a16)` and pre-table `0x00011000`; `--called all` prints 81 stubs (58 leaf), not 79 — 79 reconciles under the clamp as 77 stubs + 2 cap rows, and under it `0x00558300`/`0x00011000` become stubs (`bound 0x18`/`0x71e rts -`), so the cap class is clamp-specific (`records`/`gaps` only). `fn_match._leaf_verdict` reports `TRUNCATED` (cap `0x400`, natural bound, no `rts` in cap) instead of a false `NOMATCH` — `--va 0x00558300` now prints `TRUNCATED`, the cap and the no-`rts` clamp are unchanged, stubs stay `NOMATCH`, and the M1.28 fixture replays `13 rows, 0 mismatch`. `fn_match --selftest` covers a 0x420-B complete leaf (truncated) and a 12-B stub (not); `pdata --selftest` covers the bound/rts helpers; `selftest.py`, `claims_check`, `todo_check` OK. M1.22b's unit must be stated: `598` complete GAPs under the clamp, of which `579` leaf (19 non-leaf); a leaf rate uses `579`, not `598`, and `635`/`677` are neither.

- [x] **H101 — PM fourteenth pass: six days of board, a call graph, directions without hardware**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes
  - Note (H112, 2026-11-19): five claims of this pass are retracted (C-4281, C-4282, C-4284, C-4285, C-4286) — the graph tool counted pool words as calls. Corrected in H112 (C-4620–C-4623).
  - Depends: —
  - Goal: say how the work went since H51 (2026-11-11), and set research and development directions that need no hardware (Marek, 2026-11-17).
  - Done when: the EXP counts what closed by stream, each direction has a task with hints, and every number in it comes from a committed command.
  - Result: `docs/experiments/EXP-2026-11-17-H101-pm-review.md` (C-4280–C-4289). 33 tasks closed in six days: 22 H, 10 M1, 1 M9, none in M3/M4/M5; of H51's twelve tasks two closed. New `tools/callgraph.py` (M3.23 core): `Navi.exe` EU2011 = 9,000 nodes, 22,867 direct edges, 589 unresolved indirect calls; the map-file layer is 117 functions with three stdio wrappers; the router reader `0x004266ec` reaches 48 functions. H51's C-3488 corrected (281 code pointers in sec1 `INIT`, not 6,052). Rule 17 added.
  - Claims: C-4280–C-4289

- [x] **H106 — L3 never runs on the tile L2 actually writes: `tile_reader`'s only corpus is a factory `B28R070R`**
  - Status: done · Owner: task/h106-l3-on-l2-tile · Critical: no · Pair: required
  - Depends: M5.34 (done); M9.13/M3.25 are the entry-point work and stay their own tasks — this task only makes the corpus point at *our* tile
  - Goal: `prompt_qa.txt` asks "L3 which firmware-fragment readers ran on **our data**"; today `tools/l3_harness/targets.json`'s `tile_reader` corpus is the factory `MAPAL001/B28R070R.DAT` and the run is BLOCKED (no entry point). So even after M9.13 lands, the first L3 tile verdict would be on vendor bytes, not the `B48R058R` tile M5.34 edited. A corpus row that names M5.34's generated tile (and `one_tile_pipeline --synthetic`'s tile) makes "L3 on our data" a real row when the reader becomes runnable, and today makes the *absence* explicit instead of hidden behind one blocked target.
  - Precheck: `python3 -c "import json;print(json.load(open('tools/l3_harness/targets.json'))['tile_reader']['corpus'])"` names a factory tile; `grep -c B48R058R tools/l3_harness/targets.json` prints `0`; `python3 tools/l3check.py --build-corpus` lists `tile_reader` BLOCKED with that corpus.
  - Scope: `tools/l3_harness/targets.json` + `tools/l3check.py` reporting only — add corpus entries (`generated:m5.34:B48R058R`, `synthetic:one_tile_pipeline`) that resolve to a path when the tree is present and print `NOT RUNNABLE (no entry point)`/`NOT RUN (no tree)` with the reason; no reader work, no verdict change for the blocked target.
  - Input: `tools/l3_harness/targets.json`, `tools/l3check.py` (`--build-corpus`, corpus resolution), M5.34's EXP (tile size/hash as the provenance string), `docs/research/reader-coverage.md` rows 17–19, H43.
  - Hints: the corpus path must not be a vendor path; the row records `ran_on_our_generated_data: false` until M9.13, and flipping it is M9.13's Done-when. Keep one `tile_reader` target (two names would double the blocked count and read as progress — H107).
  - Done when: `python3 tools/l3check.py --build-corpus --json /tmp/opencode/h106.json` prints both generated corpus entries with an explicit status and reason; on a host with the M5.34 tree the status is `NOT RUNNABLE (no entry point)`, without it `NOT RUN (no tree)`; count of targets and `runnable` unchanged; `selftest.py --only l3check` PASS.
  - Stop: if M9.13 lands first and makes `tile_reader` runnable, this must assert our tile is the corpus it *ran* on (the runner's log names the path), not merely that it is listed.
  - Claims: C-4370–C-4379
  - Result: EXP `docs/experiments/EXP-2026-11-20-H106-l3-on-l2-tile.md` (C-4370–C-4373). The Stop clause applied: M9.13 made the reader runnable through `datask_l3.py mount`. This task ran it on the tile L2 actually writes (M5.11, `1927c3a9…`, dir (76,940), position 51.10,16.93): SAME as the factory over 28 reads, with the slot-table parser `0x00414dbc` (EU2011) over both changed pair entries. The header-count flip gives DIFFERENT; the synthetic tile gives DIFFERENT (directory read fails). `datask_l3 mount --json` now names the served file's SHA-256. `targets.json` `tile_reader.generated_corpus` (4 rows), and `l3check` lists them with SHA-256-driven status (`RAN (recorded: SAME)` ×2, `RAN (recorded: DIFFERENT)` for the synthetic tile, M5.34 `NOT RUN (no tree)`, no Geofabrik here; a STALE or wrong file fails the run); counts unchanged versus main. Records not read (M9.53).

- [x] **H109 — the four rule-17 map numbers are three Python one-liners, one 10-line shell loop and a host path**
  - Status: done · Owner: task/h109-map-signals · Critical: no · Pair: solo
  - Depends: — (the PO wrote the commands; this makes them portable and honest when an input is absent)
  - Goal: retro 2026-11-18 beat 4: "no log quotes the four rule-17 counters from a command". The PO's Priorities block now has them, but one is a 10-line `python3 -c` with a shell loop over `/home/marek/.../m5.4/card-factory`, so on a host without the factory tree it crashes instead of saying "NOT RUN" — and QA cannot quote it. One `tools/map_signals.py` prints all four with a stable key each, `LOCAL`/`NOT RUN` where an input is missing, `--json` for the logs.
  - Precheck: `python3 -c "import sys,pathlib;sys.path[:0]=['tools'];from progress_report import parse_reader_coverage as p;…"` (Priorities block) needs `tools/` on the path; the tile one-liner needs `tools/ze0-viewer/tools_ze0` and three `.DAT` files; the P0 one needs `/home/marek/projekty/leafre-work/m5.34/report.json` hard-coded.
  - Scope: new `tools/map_signals.py` with four subcommands or one default (`readers`, `l3_rows`, `tile_bytes`, `card_step`): reuses `progress_report.parse_reader_coverage`, the row awk from Priorities, `clarion_tile.read_tile`, and the M5.34 report's `cardcheck_ok`/`l2check_ok` — one implementation, no new numbers. Exclusion: it must not redefine any metric; if a metric needs a new definition, that is a PO task.
  - Input: the four commands in TODO Priorities (the portable contract to preserve verbatim in output keys), `tools/progress_report.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py`, M5.34's report schema (`cardcheck_ok`, `l2check_ok`, `counts.cardcheck_rc`), `docs/research/reader-coverage.md`.
  - Hints: `card_step` should read the report's booleans *and* print `counts.cardcheck_rc`, because the two can disagree (QA 16th pass: keys `cardcheck_ok`/`l2check_ok` exist beside nested `counts.cardcheck_rc`) — print both, never resolve silently.
  - Done when: `python3 tools/map_signals.py` prints the four numbers on this host; with `--factory-root` absent it prints `tile_bytes: NOT RUN (no factory tiles)` and still exits 0; `--json` carries the same keys the Priorities block uses; `--selftest` uses a tiny synthetic tile + a stub report; `selftest.py --only map_signals` PASS; the Priorities block can cite it as the one command.
  - Stop: if the reader-coverage parser is too coupled to the Markdown table to reuse, wrap it (`progress_report` stays the owner of the row semantics) and record that in the EXP; do not fork the parser.
  - Result: `EXP-2026-11-19-H109-map-signals` (C-4400–C-4406). `tools/map_signals.py` prints `readers: located 6 partial 5 unlocated 7`, `l3_rows: l3-running 1`, `tile_bytes: B28R070R 99.98%, B30R048R 95.86%, B48R058R 76.28%`, `card_step: P0 (cardcheck_ok=True l2check_ok=True counts.cardcheck_rc=0)`; absent `--factory-root` prints `tile_bytes: NOT RUN (no factory tiles)`, exit 0; `--json` carries the Priorities keys; `--selftest` (synthetic tile + stub report) `OK`; `selftest.py --only map_signals` `PASS`; the Priorities block cites it as the one command.
  - Claims: C-4400–C-4409

- [x] **H110 — the L4 row of the matrix is prose: M8.A2's boot numbers live only in the TODO block**
  - Status: done · Owner: task/h110-l4-panel · Critical: no · Pair: required
  - Depends: M8.A2 (done), M8.A10 (done); M8.A3 invents no new row, it fills this one
  - Goal: `prompt_qa.txt` requires the matrix to show "L4 full-system emulator readiness (what can run, what is blocked)". Today that is four prose lines in TODO's critical path plus the M8.A2 block; a QA pass must re-read EXP/TODO to say "QEMU 8.2.10 `-M ze0` boots one image: 10 s, exceptions 0, one unmodelled `write 0x38`" (C-4311) and "M8.E4 needs M8.A3/A6 + M9.16". A committed L4 panel with one row per stage (`F0`…`F4`), each naming its gate and blocker, and `NOT RUN` when no run log is supplied, makes the L4 delta a row instead of a paragraph.
  - Precheck: `grep -c 'M8.A3' docs/research/test-system.md` prints `0`; the only L4 statements are TODO.md's critical-path bullet and M8.A2's block.
  - Scope: `docs/research/test-system.md` (new §L4) + a small `tools/l4_status.py` (`--run-log PATH`, `--json`, `--selftest`): rows `F0 boot log`, `F1 stable kernel`, `F2 drivers`, `F3 SD mounted`, `F4 Navi.exe headless`, each with `gate`, `evidence claim`, `blocker task`, and `status ∈ PASS|FAIL|BLOCKED|NOT RUN`. `M8.A2`'s boot facts are quoted from C-4311/C-4312, not retyped from the TODO prose. Exclusion: no QEMU build in CI, no assertion that any stage passes.
  - Input: TODO M8 section (M8.A2 result, M8.A3/A6/A8/A9 blocks, M8.E4), C-4310/C-4311/C-4312, `EXP-2026-11-17-M8.A2-machine-skeleton-reprobe`, `tools/qemu-ze0/run.sh` (`--workdir` log names), `docs/research/test-system.md` §status classes.
  - Hints: `--run-log` should read `run.sh`'s summary keys only (exceptions count, unmodelled accesses, wall clock) — those exist; anything absent is `NOT RUN`, never inferred. The panel is readiness, not acceptance (rule 13): say "boots one image", not "L4 pass".
  - Done when: the §L4 table exists with six rows and no bare numbers (each names its claim); `python3 tools/l4_status.py` prints the table and exits 0 with `F4 BLOCKED (M8.A3, M8.A6, M9.16)`; without a run log every F-row is `NOT RUN`; `--selftest` proves the five statuses and that a missing key is NOT RUN; `selftest.py --only l4_status` PASS.
  - Stop: if `run.sh`'s summary format is unstable, print the statuses from the committed table only and mark `--run-log` as best-effort in the docstring.
  - Result: `docs/experiments/EXP-2026-11-20-H110-l4-panel.md` (C-4410–C-4418; C-4419 reserved). New §L4 in `docs/research/test-system.md` (F0 boot log, F1 stable kernel, F2 drivers, F3 SD mounted, F4 `Navi.exe` headless, log reader; each names its gate and evidence claim C-4311/C-1352/C-1353/C-537) and `tools/l4_status.py` (`--run-log`, `--json`, `--selftest`). `python3 tools/l4_status.py` prints the table, exits 0, `F4 BLOCKED (M8.A3, M8.A6, M9.16)`; without a log every F-row is `NOT RUN`; a clean log moves only F0 to `PASS` and a non-zero count is `FAIL`; `--selftest` proves the five checks; `selftest.py --only l4_status` PASS.
  - Claims: C-4410–C-4419

- [x] **H112 — PM fifteenth pass: where we are on 2026-11-19, a corrected call graph, next steps**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes
  - Depends: —
  - Goal: Marek, 2026-11-19: look at where we are, write corrections, hints and remarks into the TODO, plan the next steps.
  - Done when: the review's numbers come from committed commands, wrong statements of the previous pass are retracted in the ledger, and each next step is a task with hints.
  - Result: `docs/experiments/EXP-2026-11-19-H112-pm-review.md` (C-4620–C-4629). Since H101: 21 tasks done, 19 of them outside H (M1 1, M3 2, M4 1, M5 9, M8 2, M9 4), 2 in H, and H92 recorded as blocked; P0 card done; readers 6/30 and L3 1/30 unchanged. `tools/callgraph.py` fixed (pool words were decoded as calls: 2,201 false EU edges) and names imports by ordinal; five H101 claims retracted. New: the file-name tables and their loaders (the `MAPAL001` open path `0x0040b850` → `0x0040b3e0` → `0x0040a108` → `0x004192c0`). New task M3.28; notes on M3.23, M3.24, M3.25, M4.40, M9.2, M9.44.
  - Claims: C-4620–C-4629

- [x] **H116 — the DOCS BASE corpus pins citations inside *done* TODO blocks, so archiving a finished task reddens the standing gate on a host with the image**
  - Status: done · Owner: task/h116-archive-vs-docs-base · Critical: no · Pair: required
  - Depends: — (found by the cycle-17 PO archive pass, 2026-11-20)
  - Goal: `tools/fn_audit.py --corpus docs/research/fn-audit-corpus-2026-11-16.json` (DOCS BASE) discovers VAs in `TODO.md` as a whole, including blocks whose `Status: done`. The PO rule ("archive done blocks >24 h old that no live task names") therefore cannot be followed: moving 9 such blocks to `docs/research/todo-history-2026-11-20.md` changed the docs-base identity set by `0 new / 17 gone / 151 moved` and made `tools/selftest.py`'s `fn_audit_l3_image` fail on a host with `archive/head256.img`. CI skips that suite (no image), so the regression is invisible to CI and only bites the TL/QA gate run. Archiving must be safe: a done block's VAs are history, not live citations.
  - Precheck: on a clean `origin/main` with `archive/head256.img`, copy 5 done blocks out of `TODO.md` into a scratch file and run the corpus command above — expect `CORPUS STALE: ... gone`; restore and it is `0 new / 0 gone`. Confirms the corpus covers done blocks.
  - Scope: `tools/fn_audit.py` `citations_open_tasks`/`_open_blocks` (and, if needed, the docs-base collection that reads `TODO.md`) — the DOCS BASE scan must follow the same live-block definition the l3 open-block scan uses (H115), i.e. only `open`/`in progress`/`blocked` blocks are cited; `docs/research/fn-audit-corpus-2026-11-16.json` re-frozen once against the narrower definition (this re-freeze is the expected, intentional change — record it in the EXP with before/after counts). Add a `--selftest` case: a synthetic board with one done block carrying a `0x…` and one open block; only the open one is cited.
  - Input: `tools/fn_audit.py` (collect/collect_l3, `DOC_FILES`, `_open_blocks`, `citations_open_tasks`), `tools/selftest.py::test_fn_audit_scope_l3_image`, `docs/research/fn-audit-corpus-2026-11-16.json`, the cycle-17 PO attempt (9 blocks: M1.16, M1.23, M1.29, M3.2, M3.19, M4.20, M5.10, M5.12b, M8.E1b).
  - Done when: after the fix, moving a *done* block with a unique VA into a history page leaves `fn_audit ... --corpus <base>` at `0 new / 0 gone` (negative control: moving an *open* block's VA out still reports the `gone` row and exits 1); the refreshed corpus contains no row whose only home is a done block; `python3 tools/selftest.py` and `python3 tools/gate.py` are green on a host with the image; the EXP records the pre/post corpus row counts. **Then** the PO may re-run the archive (a separate pass; this task only makes it safe).
  - Stop: if the docs-base scan is intentionally whole-file (a citation anywhere in `TODO.md` is proof), do not narrow it — instead make the archive tool strip or move the block's citations in the same commit and record that the corpus is a whole-file snapshot; the task closes with that decision and a `docs/research` note, not with a silent corpus edit.
  - Claims: C-5740–C-5749
  - Result: done — EXP-2026-11-20-H116-archive-docs-base. DOCS BASE now cites only live TODO blocks (`live_todo_lines`, `_open_blocks` span; a done block is history); corpus re-frozen once 609→466 rows (TODO.md 168→25, non-TODO 311 keys unchanged). Moving the cycle-17 nine done blocks is `0 new / 0 gone / 25 moved` exit 0 (pre-fix at branch base `d2fb7b4`: `0 new / 17 gone / 151 moved`, exit 1); moving the blocked M3.13 block still `0 new / 5 gone / 16 moved`, exit 1. gate 4 pass/0 fail/0 skip.

- [x] **H113 — `fn_match` blanks real instructions as pool slots when pool data decodes as `mov.x @(disp,PC)`**
  - Status: done · Owner: task/h113-fnmatch-pool · Critical: no · Pair: required
  - Depends: H89 (done; the PHANTOM-SLOT class and its count)
  - Goal: `fn_match._instruction_tokens` and `fingerprint` mark a pool slot for every halfword that decodes as a PC-relative load, including halfwords that are themselves pool data, and then hash a real instruction as `0x0000`. H89 (C-4123) found `141` of the 1259 NOMATCH that differ only by such a phantom slot; a forward pass (a halfword already marked as a slot never names another one; PC loads only reach forward) gives each a unique US digest, and address-order pairing (131 anchor, 10 gap/global) names the same US function in 141/141.
  - Precheck: `python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all | grep 'forward-pass'` prints `forward-pass digest unique in US: 141 of 1259 (the anchor pairs the same US function in 141)`; `python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va 0x0033d00c` prints `NOMATCH`.
  - Scope: `tools/fn_match.py` slot derivation (`fingerprint`, `_instruction_tokens`, `pool_masked` if it shares the flaw) + selftest case + re-pinned census numbers (C-3626 is then historical: say so with a revision, never edit the old count in place); `tools/fixtures/fn_match_eu_us_2011.json` must still replay `0 mismatch`.
  - Input: `tools/nomatch_census.py` (`pool_slots`, `naive_slots`, `phantom_sources`, `--pair`), EXP-2026-11-20-H89-nomatch-census, C-3626.
  - Hints: reuse `nomatch_census.pool_slots` rather than writing a second pass. The change also alters UNIQUE hashes on both sides, so re-run the full census and report every verdict that moves, not only the 141.
  - Done when: an EXP gives the new module census with the before/after verdict table; `0x0033d00c` is no longer `NOMATCH`; the fixture replays `0 mismatch`; `python3 tools/gate.py` green.
  - Stop: if any `UNIQUE` pair of the old census changes its US address, stop and record it instead of merging the change.
  - Claims: C-5570–C-5579
  - Result: docs/experiments/EXP-2026-11-20-H113-fnmatch-pool.md; C-5570–C-5576. One forward slot pass (`pool_slots`/`_pool_loads` in `tools/fn_match.py`, `nomatch_census.pool_slots` delegates) feeds `fingerprint`, `_instruction_tokens`/`code_digest` and `pool_masked`; `fn_match --selftest` 41→46. Module census `UNIQUE 5945 / DIFFERENT 171 / CALLORDER 56 / AMBIGUOUS 566 / NOMATCH 858` (was `2392/3214/213/518/1259` at `d2fb7b4`, C-3626 historical); 0 rows move to another non-null US, all 3028 `DIFFERENT`→`UNIQUE` are phantom-slot, 129 of the 141 forward-pass rows are `UNIQUE` + 12 `DIFFERENT` to the same US. `0x0033d00c` is now `UNIQUE → 0x0036bb5c`; fixture 6 rows `DIFFERENT`→`UNIQUE` (same US VAs), replay `13 rows, 0 mismatch`; 6 old `UNIQUE` are now `AMBIGUOUS` (twin runs, never guessed). `gate.py` 4/4. Known residual (open, H118): an *unloaded* pool-data word that decodes as a load still blanks a real instruction; the marked-slot rule covers only words a load already named.

- [x] **H114 — `fn_match` refuses an identical masked stream with two or more US twins; address order can pick one**
  - Status: done · Owner: task/h114-fnmatch-twin · Critical: no · Pair: required
  - Depends: H89 (done; the TWIN class), H113 (land the slot fix first so the twin counts are final)
  - Goal: `_pool_only_twin` returns `None` when the masked form stream has ≥2 US twins. H89 (C-4122) found `219` such NOMATCH (13/40 in the sample, the largest class), `188` of them with an exact address-order anchor: the matched neighbours on both sides bracket a US gap of the same size, and the record at the same offset is one of the twins. Pairing those as `DIFFERENT`/`ANCHOR` (a new, separately counted verdict) would locate them by address order.
  - Precheck: `python3 tools/nomatch_census.py archive/head256.img archive/us256.img --all | grep '^#   anchor '` lists `TWIN 188`; `python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va 0x003c0108` prints `NOMATCH`.
  - Scope: `tools/fn_match.py` only (a new verdict, reported separately from `UNIQUE`, never used for a twin outside an exact same-size anchor gap) + selftest + census EXP; no change to `UNIQUE`/`DIFFERENT` semantics.
  - Input: `tools/nomatch_census.py` (`anchor_candidates`, the `control+`/`control-` lines), EXP-2026-11-20-H89-nomatch-census.
  - Hints: H89's positive control re-paired 38/40 UNIQUE through the anchor; repeat it with a larger sample before trusting the new verdict, and keep the 21 order inversions in the anchor list out of the pairing.
  - Done when: an EXP reports how many TWIN rows get the new verdict and a positive control (UNIQUE functions re-paired by anchor ≥95 %) and a negative control (a shuffled anchor pairs 0 twins); a ±1 shifted-anchor control re-pairs 0 TWIN rows to the same US twin, or rows whose ±1 neighbour is also a twin are listed and excluded; the verdict is one-to-one (no US twin claimed by two EU rows — H89's `--all` run names 30 US records from more than one row, e.g. EU `0x003c3a34` and `0x003c3ad8`); `python3 tools/gate.py` green.
  - Stop: if the positive control falls below 95 %, record it and leave the verdict out.
  - Claims: C-5700–C-5709
  - Result: done — EXP-2026-11-20-H114-anchor-twin. `fn_match` gains an `ANCHOR` second pass (`anchor_verdicts`, `anchor_candidates`, `anchor` subcommand, `--no-anchor`): a multi-twin `AMBIGUOUS`/`NOMATCH` row whose exact same-size gap names one of its twins and whose US target is unclaimed is located by address order; `UNIQUE`/`DIFFERENT` unchanged. It fires on `401` rows (392 `AMBIGUOUS`, 9 `NOMATCH`); census `UNIQUE 5945  DIFFERENT 171  CALLORDER 56  ANCHOR 401  AMBIGUOUS 174  NOMATCH 849`, 0 moved base US, 0 extra US claims (one-to-one). Positive control 5543/5550 = 99.87 % of pairable (93.24 % of all UNIQUE; 395 have no exact gap), shuffle 0, ±1 shift 0 same-twin re-pair. H89's `TWIN 219` is historical; `0x003c0108` is `AMBIGUOUS`→`ANCHOR` (C-5700–C-5706; C-5707–C-5709 unused).

- [x] **H118 — `fn_match` still blanks real instructions when UNLOADED pool data decodes as `mov.x @(disp,PC)`**
  - Status: done · Owner: task/h118-fnmatch-unloaded-pool · Critical: no · Pair: required
  - Depends: H113 (done; the marked-slot rule and its residual)
  - Goal: H113's forward pass exempts only a halfword **already named** as a slot. Pool data that no load names (a data run after the function's own loads, alignment words, a literal a dead load pointed at) still decodes as `mov.x @(disp,PC)` and names a slot that lands on a real instruction, which `fingerprint`/`_instruction_tokens` hash as `0x0000` and `pool_masked` zeroes. Synthetic control: `hw0 = 0xD702` (loads hw6), `hw6 = 0xDA39` (loaded, exempt), `hw50 = 0xD023` (named by no load), `hw122 = 0xC11E` → `pool_slots` contains 122, `_instruction_tokens[122] == 0x0000`, `pool_masked[122] == 0`. Measure how many of the 858 H113 NOMATCH (and how many `DIFFERENT` rows) are this residual, then narrow the slot rule (e.g. a slot target must lie in the function's own trailing pool region, or a slot may only be named by a load whose target is not past the last instruction the `.pdata` length covers).
  - Precheck: `python3 tools/fn_match.py --selftest` is `OK (46 checks, 0 failed)`; the residual script in EXP-2026-11-20-H113-fnmatch-pool's Observations (synthetic hw50) reproduces `122 in slots: True`, `tokens[122]: 0000`, `masked[122]: 0`.
  - Scope: `tools/fn_match.py` slot derivation (`_pool_loads`/`pool_slots`) + selftest + census EXP; no change to `UNIQUE`/`DIFFERENT` semantics beyond the phantom class. Not: `_pool_only_twin` (H114).
  - Falsifier: if narrowing the rule moves any row's non-null US address to a different non-null one, stop and record it (H113 Stop).
  - Done when: an EXP gives the before/after census and the count of rows the residual explains; the synthetic hw50 case no longer blanks hw122 (selftest) while the loaded-pool-word case still does not; `python3 tools/gate.py` green and the `fn_match_eu_us_2011.json` fixture replays `0 mismatch`.
  - Stop: if no narrowing rule keeps every H113 `UNIQUE` US address, record the negative with the count and leave the residual documented instead of merging a behaviour change.
  - Claims: C-5800–C-5809
  - Result: docs/experiments/EXP-2026-11-20-H118-fnmatch-unloaded-pool.md; C-5800–C-5806. `_pool_loads` walks the function from its entry (`reachable`) and rejects a slot on a reached instruction and, in a function with no reached `braf`/`jmp`, a load at an unreached halfword; the hw50 synthetic no longer blanks hw122, the loaded-pool case still does not (`fn_match --selftest` 46→53). Census `UNIQUE 5954 / DIFFERENT 162 / CALLORDER 56 / AMBIGUOUS 566 / NOMATCH 858` (was `5945/171/56/566/858`): only `DIFFERENT→UNIQUE 9`, same US VAs, 0 moved; the residual explains 0 of the 858 NOMATCH (31 contain such a load, none changes) and 9 of 171 `DIFFERENT` (8 were reads of the next function's bytes past the function end). Control: dropping every unreached load (`--all-closed`) loses 48 `UNIQUE` to `NOMATCH` (switch case bodies). Fixture `13 rows, 0 mismatch`, `bodies` 12/12 unchanged. New `tools/fn_verdict_diff.py` (dump/diff/slots).

- [x] **H119 — Two task PRs that each add an EXP always conflict in the fn_audit snapshots**
  - Status: done · Owner: task/h119-fn-audit-snapshot-conflict · Critical: yes · Pair: required
  - Depends: — (serves the map tasks whose merges it holds up: M9.55, M3.29, M9.53 waited 21–35 merges behind `main`, retro 2026-11-20-2)
  - Goal: a task PR that adds a correct `fn` citation must not have to rewrite `docs/research/fn-audit-corpus-2026-11-16.json` or `fn-audit-l3-corpus-2026-11-20.json`. Today a `new` row is `CORPUS STALE` (exit 1), so every PR re-freezes both files; they hold one row per citation **with its line number**, so two PRs always conflict and the loser merges `main`, re-syncs and pushes again. Measured 2026-11-20 10:03Z–18:09Z: `git log 8f18cbf..13cb0cf --format=%s | grep -ciE "re-sync|re-freeze|refresh.*snapshot"` printed 25, and `git log 8f18cbf..13cb0cf --format=%h -- docs/research/fn-audit-l3-corpus-2026-11-20.json | wc -l` printed 85.
  - Precheck: in a scratch clone, two branches from one commit each add one EXP that cites a different `START` VA and run `fn_audit … --write-snapshot`; `git merge` of the second reports a conflict in a snapshot file (the defect).
  - Scope: `tools/fn_audit.py`, `tools/gate.py` and the two snapshot files. Pick one, say which in the EXP: (a) the gate fails only on a `gone` row, a verdict change, or a `new` row whose class is not `START`/`CORRECTED`/`leaf`; valid new rows are reported and the snapshot is re-frozen on `main` only (one commit per TL batch or a scheduled job); or (b) the snapshot is stored one row per line without `line`, sorted by `(file, va, kind)`, with a `merge=union` attribute and the summary recomputed, so parallel additions merge as text. H69's protections stay: a lost duplicate and an `INSIDE` citation still fail.
  - Input: `tools/fn_audit.py` (`compare_live`, `_audit_layer`, `--write-snapshot`), EXP-2026-11-16-H69-snapshot-refresh, EXP-2026-11-20-H77-skip-fenced-code, EXP-2026-11-20-H116-archive-docs-base.
  - Done when: `fn_audit --selftest` builds the Precheck's two branches in a temp repo and their merge has no conflict in either snapshot in both orders, `python3 tools/gate.py` is green on the merge commit without a re-sync commit, and two negatives still exit 1: one cited `START` VA deleted from an EXP, and one new citation of an `INSIDE` VA. EXP with the before/after counts of the two commands in Goal on a replayed five-PR window.
  - Stop: if (a) lets a wrong citation through in the negative and (b) cannot keep the count check, record both and keep today's policy with the re-freeze moved to one TL commit per batch.
  - Falsifier: a merge of two PRs that needs a snapshot re-sync commit after this task lands.
  - Claims: C-6330–C-6339
  - Result: EXP-2026-11-21-H119-snapshot-union-merge; v2 one-row-per-line no-line merge=union, 2-order merge clean, 2 negatives exit 1, 107/107 selftest, gate 4 pass

- [x] **H123 — `tools/board.py`: edit `TODO.md` and `claims.md` by line operations, never by rewriting the file**
  - Status: done · Owner: claude/project-thread-1tslvr · Critical: yes · Pair: solo
  - Depends: —
  - Goal: agents (LLMs) rewrite `TODO.md` (5k lines) and `claims.md` (4.5k lines) whole and lose what they did not read: PR #340 dropped 787 + 324 lines (H121). A script does each board change as one splice (claim, set a field, close, add a task block, add a claim row, take the next free ID / claim block, resolve a merge conflict by ID) and refuses any write that drops a task ID or claim ID or changes the line count by other than the operation's own delta (Marek, 2026-11-21).
  - Scope: `tools/board.py` with `--selftest`; AGENTS.md, `TODO.md` rules 3/5/6/9 and the role prompts name it as the way to edit the two files. H121 (the CI check against the merge base) stays a separate task; it reuses `board.lost_ids()`.
  - Input: `tools/todo_check.py` (`TASK_RE`, `FIELD_RE`), `tools/claims_check.py` (`ROW_RE`), PR #340 / commit `6ca7bc3`.
  - Done when: `python3 tools/board.py --selftest` passes; on `6ca7bc3` `python3 tools/board.py lost --base 4900961 --head 6ca7bc3` exits 1 and names M9.56–M9.62; `tools/fixtures/h123-board-conflict-replay.sh` keeps both branches' task blocks and claim rows; `todo_check.py` and `claims_check.py` stay green.
  - Falsifier: an edit through `board.py` that changes a line outside its own splice, or a `resolve` that drops an ID present on either side.
  - Claims: C-6580–C-6589
  - Result: EXP-2026-11-21-H123-board-tool (C-6580–C-6584): `board.py --selftest` OK (58 checks); `lost` on `6ca7bc3` names 42 tasks and 199 claim rows (exit 1); the conflict replay keeps both sides' tasks and rows and leaves only the two-sided H122 edit; AGENTS.md, TODO rules 3/5/6/9 and the role prompts name the tool.

- [x] **M3.26 — Name the map-file layer of `Navi.exe`: 117 functions, three stdio wrappers, one dispatcher**
  - Status: done · Owner: task/m3.26-nav-file-layer · Critical: yes · Pair: required
  - Depends: — (H101: `tools/callgraph.py` and the graph are reproducible from IMG256)
  - Goal: every map file the unit reads goes through one block of code, `0x00417d00…0x0041cab0` (EU2011). It contains the `fopen`/`fseek`/`fread` wrappers, the `.cmp` chunk engine, the `DRSTR` and `MMAIN` readers and the media-mount state machine. Nobody has a list of its functions with roles. With that list each reader task starts from a named entry instead of a search.
  - Precheck: `python3 tools/callgraph.py build IMG256 -o g.json` prints `functions 9000 … unresolved indirect calls 589`; `python3 tools/callgraph.py users g.json fread,fseek,fopen` lists `0x0041b4f8` (fread), `0x0041b470` (fseek, ftell), `0x0041b3bc` (fopen) among the hits.
  - Scope: the 117 graph nodes in `0x00417d00…0x0041cab0`, EU2011 build A only. For each: pdata start and length, callers, callees, imports, and a role in at most eight words. No format claims; a role that cannot be read from the code in ten minutes is `unknown`.
  - Input: H101 measured — `fread` wrapper `0x0041b4f8` has five callers: `0x00418a10`, `0x00418b00`, `0x00419350` (DRSTR parser), `0x0041b2a4`, `0x0041b954`; `0x0041b954` is called by `0x0041a438` (MMAIN) and `0x0041855c`; thirteen functions of the block are called from outside it, nine of them only by `0x00417924` (a dispatcher, itself called from `0x0032efa8`, the function with 25 indirect calls that looks like the task table); `0x004192c0` is the entry the `REFER` path (`0x0040b358`) and four functions next to the `LEV3456R` name load (`0x00409ba0`, `0x00409c28`, `0x00409cc8`, `0x0040a108`) call; the `.cmp` chain is `0x0041b954`/`0x0041ba90` → `0x0041c044` → `0x0041c990` → `0x0041c7dc` → zlib.
  - Hints: start from the three wrappers and go up two levels with `callgraph.py callers g.json VA --depth 2`; the functions that call both `fseek` and `fread` wrappers with a constant size are the fixed-header readers. `0x0041c124` has four unresolved calls: it is the place where a per-file handler table is used — find the table (a run of function addresses in sec0 below `0x0032ed9c`, located with `sh4xref --to`). The debug strings passed to `NKDbgPrintfW`/`OSM_Printf` in each function are free names: print the literal each call loads.
  - Done when: `docs/format/firmware.md` has the table (117 rows, build named), the dispatcher's message numbers → handler map, and the answer to M3.2's two questions (where `chunk_size` comes from, seek or scan) read off `0x0041c990`; `tools/l3_harness/targets.json` gets no new target (that is M9.44).
  - Stop: after the table; a function whose role stays `unknown` is listed, not investigated.
  - Falsifier: a map file read that does not pass through this block (found by `callgraph.py users` on `ReadFile`/`MapViewOfFile` with a caller on a map path) — then the block is not the whole layer and the table says so.
  - Claims: C-4440–C-4449
  - Result: EXP-2026-11-18-M3.26-file-layer. `docs/format/firmware.md` has the
    117-row table (117 map-file-layer nodes, 109 `START` / 8 `GAP` / 0
    `INSIDE`, EU2011 build A, `pdata --index 2`), the 12-message → handler map
    (`0x0017a888`) and the `(state*5+kind)` 4x5 table (`0x0017ab38`). `.ind`
    header order is measured on all 2,875 `.ind` files under
    `~/projekty/leafre-work` — `(logical, compressed, count, chunk)`, with
    `chunk == 0x10000` and `count == ceil(logical/chunk)` in every one (command
    prints `2875 2875`); the `_divlu` divisor is B at `head+12` (the chunk
    size, the word compared with `ctx+0x138`). The dispatcher branches with
    `braf r0`, `target = 0x417d74 + offset`, and `0x417924` has one static
    caller, `0x32efa8` (`0x4180f0` is a graph false edge). Falsifier did not
    fire (13 Win32-file-API users, `no static path` from `0x40b358`);
    `targets.json` untouched (M9.44).

- [x] **M3.27 — M3.25's first half: the tile reader's entry arguments, static, no run**
  - Status: done · Owner: task/m3.27-tile-reader-args · Critical: yes · Pair: required
  - Depends: M3.5 (done — the three reader VAs), M1.26 (done — the audit that found one entry mid-function)
  - Goal: M3.25 needs both an entry VA and its calling convention before an L3 run can be trusted, and the argument half is a disassembly task with no emulator: which register carries the tile pointer, which the section/level, what the return convention is, and whether the third "reader" VA is a thunk of the first. Splitting it off makes the L3 run (M3.25) one variable instead of a search plus a harness in one pass; PR #229 proposes the same split.
  - Precheck: `python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x0042c4b0` (or the VAs M3.5 records) prints START/INSIDE/GAP for each of the three; `python3 tools/sh4dis.py archive/head256.img --va <entry>` prints the prologue.
  - Scope: `docs/format/map-tiles.md` gains the entry table (VA, build, pdata length, argument registers r4..r7 with the meaning each is shown to carry, return register, and the call sites that set them), plus a claim row per register that a disassembly can support. No run, no harness change, no new VA unless the prologue proves one.
  - Input: M3.5's three VAs, M1.26's mid-function finding, `tools/sh4dis.py`, `tools/nk_decomp.py`, `tools/callgraph.py` (callers that set r4..r7), EXP-2026-11-06-M3.6 (the MAP_DATA/RGD_DATA split).
  - Hints: the callers are the evidence — a register is "the tile pointer" only if every caller loads it from a tile base; say which callers disagree and why. If a register carries two meanings at different call sites, record both rather than picking one.
  - Done when: `docs/format/map-tiles.md` has the entry table with a build name on every VA; every argument register names the caller that sets it; `python3 tools/claims_check.py --strict --count-check` green; `python3 tools/gate.py` 4 pass.
  - Stop: if two call sites genuinely disagree on a register and the code does not resolve it, record both readings and block the register, not the task.
  - Falsifier: a register is named from one caller while another caller loads a different base into it, and the table does not say so.
  - Note (M3.27 driver, 2026-11-19): result is in `docs/format/map-tiles.md` §"Reader entry arguments" and EXP-2026-11-19-M3.27-tile-reader-args (C-4580–C-4589). `0x0042757a` is `INSIDE` `0x00427578`, so the third entry is `0x00427578`; all three have exactly one static call site and none takes a tile buffer (`r4` is a record pointer for `0x0041f26c`/`0x00427578`, a mesh id for `0x004259bc`), so M3.25/M9.13 should target or wrap `0x00425f40` rather than inventing the `(tile, dst)` prototype.
  - Result: EXP-2026-11-19-M3.27-tile-reader-args.md — the tile-reader entries' arguments from `.pdata` and the sole call sites: `0x0041f26c` (r4 record pointer, r5 a 4-entry u32 array, r6 flag/mode UNKNOWN, r7 dead), `0x004259bc` (r4 mesh id, r5/r6 local, r7 control flag, the call reached only when r7 != 0), `0x00427578` (r4 20-byte record pointer, r5/r6/r7 overwritten; M3.5's `0x0042757a` is INSIDE it). None takes a tile buffer and none sets a deliberate return value, so M3.25/M9.13 must target or wrap `0x00425f40` instead of the invented `(tile, dst)` prototype. Every row is a claim (C-4580-C-4589) with its decoding command; gate 4 pass, claims_check OK, fn_audit 0 new/0 gone.
  - Claims: C-4580–C-4589

- [x] **M5.51 — `imgpatch --check-diff` names the 9 metadata ranges but not *which FAT link* each is; a card-diff reader must**
  - Status: done · Owner: task/m5.51-metadata-reasons · Critical: no · Pair: required
  - Depends: M5.30 (done — 586 ranges / 152,815 B, outside 0 wide / 9 strict), M5.47 (done — the allocator identity)
  - Goal: M5.30's `--allow-metadata` passes a card whose 9 metadata ranges are "FAT/FSInfo sectors", but the class is **whole-sector**: the navigator planted a byte at a FAT0 entry and an FSInfo offset and both were reported `metadata 11 ranges / 26 B, outside 0`. An auditor cannot tell, for the real 9 ranges, whether each is a link the relocation *must* change (`FAT[old]=free`, `FAT[last]=new`, `FAT[new]=EOF`) or slack in the same sector. Without a per-range reason the guarantee "the diff is the relocation, nothing else" is one byte wide and untested.
  - Precheck: `python3 tools/imgpatch.py --image <CARD> --reference <IMG> --file MAPAL001/B48R058R.DAT --file DRSTR001.DAT --check-diff --allow-metadata` prints `metadata: 9`; with the navigator's planted FAT0 byte it prints `metadata: 11` (the whole-sector class to name per range). Asset: the M5.30 card `b0faf119…` (rebuild from EXP Reproduction if absent; scratch in `~/projekty/leafre-work/scratch/m5.51/`).
  - Scope: `tools/imgpatch.py` `--check-diff` only: for each metadata range print a **reason** (`fat0_link`, `fat1_link`, `fsinfo_free`, `fsinfo_nxt`, `fsinfo_unknown`) from the FAT entry index the range covers and the old/new chain, plus a `--strict-metadata` that fails any metadata range whose reason is not an expected link field. EXP records the 9 real ranges with their reasons and the planted controls.
  - Input: EXP-2026-11-19-M5.30-one-variable-card §5/§6 and C-3063, EXP-2026-11-19-M5.47-fit-census (allocator identity), `tools/imgpatch.py` (`_classify_range`, `--check-diff`), `tools/mkcard.py` (`diff_ranges`, FAT geometry).
  - Hints: the three link fields for a move are `FAT[old_cluster] -> 0`, `FAT[new_cluster] -> 0x0FFFFFFF` (or next), and the chain neighbours; a 512-byte FAT sector holds 128 entries, so one sector change can span up to 128 links — the reason must be per *entry* the range covers, not per sector. FSInfo has free-count and next-free; a relocation changes both, and no other field may change in strict mode.
  - Done when: the 9 real ranges each carry a reason printed by the tool; `--strict-metadata` exits 0 on the M5.30 card and non-zero on the navigator's planted FAT0-entry mutant and the FSInfo-offset mutant (two negative controls, outputs pasted); `--selftest` covers a per-entry reason and the strict refusal; `python3 tools/selftest.py`, `tools/gate.py` green; EXP + claims.
  - Stop: if a FSInfo field cannot be tied to the move with the bytes available, print `fsinfo_unknown` and keep strict refusing it — an unknown reason is a result, not a reason to widen the allowlist.
  - Falsifier: a metadata range outside the move's own `FAT[old]`/`FAT[new]`/neighbour links + FSInfo counters is labelled `fat*_link`/`fsinfo_*` and strict mode passes it.  - Result: EXP-2026-11-19-M5.51-metadata-reasons.md (C-4610-C-4619). `imgpatch.py --check-diff --strict-metadata` names every admitted metadata range and fails any that is not a link of the move. On card `b0faf119...33237` it exits 0 with `metadata: 9`, `unexpected metadata: 0`, and the nine ranges are exactly FAT[94806] 268435455->29687, FAT[29687] 0->29688, FAT[29688] 0->268435448 in both copies plus the FSInfo free/next words. Two negative controls (FAT0 entry 50000 -> `fat0_slack`, FSInfo sector-1 0x100 -> `fsinfo_unknown`) exit 1; wide `--allow-metadata` still admits both, so M5.30's numbers are unchanged. `--selftest` 73 checks; selftest.py 96/0/24; gate 4/0/0. Review was in-process (subagent router down), recorded as self-review in the EXP.
  - Result: EXP-2026-11-19-M5.51-metadata-reasons.md (C-4610-C-4619). `imgpatch.py --check-diff --strict-metadata` names every admitted metadata range and fails any that is not a link of the move. On card `b0faf119...33237` it exits 0 with `metadata: 9`, `unexpected metadata: 0`; the nine ranges are exactly FAT[94806] 268435455->29687, FAT[29687] 0->29688, FAT[29688] 0->268435448 in both copies plus the FSInfo free/next words. Two negative controls (FAT0 entry 50000 -> fat0_slack, FSInfo sector-1 0x100 -> fsinfo_unknown) exit 1; wide `--allow-metadata` still admits both, so M5.30's numbers are unchanged. `--selftest` 73 checks; selftest.py 96/0/24; gate 4/0/0. Review was in-process (subagent router down), recorded as self-review in the EXP.
  - Claims: C-4610–C-4619

- [x] **M3.33 — Why the mount leaves `B60R048R.DAT` after its header**
  - Status: done · Owner: task/m3.33-b60-header-drop · Critical: no · Pair: solo
  - Depends: M3.31 (done)
  - Goal: at 65.0 N 30.0 E and 64.5 N 29.0 E, both inside the `0x2ac` boxes of EU2011 `B60R048R.DAT`, `datask_l3.py mount --position` reads that tile's header and then the directories of `B28R070R.DAT` (C-5825). Find the check that drops the tile (header handler `0x0040b8b4` and what it decides), so a generated tile outside the factory set is not dropped the same way.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image <EU card> --position 65.0,30.0 --json P1.json` shows one `B60R048R.DAT` read (`0x1000`, handler `0x0040b8b4`) and directory reads of `B28R070R.DAT`.
  - Scope: EU2011 `Navi.exe`; the header handler and the position-to-tile choice (`0x0040b49c`, the global at `0xd940e4`). Excludes record blocks.
  - Input: EXP-2026-11-20-M3.31-dir-read-length (runs P1, P1c), EXP-2026-11-20-M9.13-generated-tile-l3 (position check), `tools/datask_l3.py`.
  - Done when: the branch that leaves `B60R048R` is named with its VA and the header field it tests, and a run that changes that field (or the position) makes the mount read `B60R048R`'s section tables.
  - Stop: one session; if the choice depends on a table filled by a task not in the run, name the table and its writer and block.
  - Claims: C-6080–C-6089
  - Result: `docs/experiments/EXP-2026-11-20-M3.33-b60-header-drop.md` (C-6080–C-6087), new `tools/tile_drop_l3.py`. The branch is `0x0040ad36`–`0x0040ad78` → `0x0040ae26` of the header check `0x0040acb8` (EU2011): every tile box asks for three parts, and a tile whose **third section-list entry (header `0x80c`) is `ff ff ff ff`** gets box status 3 and is left on the first mount; the box finder then skips it, answers -1, and the caller takes that as box 0 (`B28R070R.DAT`). Causal controls: `B60R048R` with a third entry written mounts (3 section tables); `B48R058R` with its third entry removed is left. 8 of the 45 factory tiles list fewer than three sections. Rule for the generator: list three sections (the fresh container already does). Follow-up: M5.62.

- [x] **M5.63 — POI writer: fine position, spatial-tree leaf and index records for a moved or added POI**
  - Status: done · Owner: task/m5.63-poi-position-writer · Critical: yes · Pair: solo
  - Depends: M4.27 (done), M5.26 / M4.47 (chain regeneration and relocation, done); M3.34 strengthens the gate but does not block the build
  - Goal: the POI tools rename only (`mutate_refer_poi.py`, `point_pair_regen.py`). A POI for Poland needs a position: copy A with the `11xx` nibble, the two fine words, and the same values in the leaf of its category's spatial tree; a new POI also needs its index records, trie entries and (US) phone key. Build the first step: move one existing POI to a given lat/lon and keep every structure `point_census.py` checks consistent.
  - Precheck: `python3 tools/point_census.py --selftest` passes; `python3 tools/point_census.py joins DIR --files POINT010` prints `joins hold` on a factory pair.
  - Scope: one `POINTnnn.DAT` pair. Step 1 (required): move within the same copy-A cell (name record bytes 6–9 and the leaf `fine` word only). Step 2 (if time): move to another cell of the same level-1 node (leaf moves between nodes of the spatial tree). No new POI, no trie change.
  - Input: `tools/point_census.py` (`encode_position`, `walk_spatial`, `census`), `tools/point_pair_regen.py` (page re-pack), EXP-2026-11-20-M4.27-point-census-fine-position.
  - Done when: a tool with `--selftest` writes a pair in which the chosen POI decodes to the requested position within 2 m, `point_census.py census` and `joins` pass on the output, every other byte outside the touched page and leaf is unchanged, and a no-op run is byte-identical; negative control: a pair with the record moved but the leaf left is refused by `joins`.
  - Stop: one session.
  - Claims: C-6550–C-6559
  - Result: EXP-2026-11-21-M5.63-poi-move (C-6550–C-6559): `tools/point_move_poi.py` (`--selftest`, 21 ok; host-independent on python3 zlib-ng, python3.13 and python3.11 stock 1.3.2) moves record 0 of EU 2011 `POINT010` 1.95 m from the request (52.572276,-9.282440), census `unaccounted=0`, joins 15,378/15,378, 0 bytes changed outside the page slot and leaf, `cmpind verify` PASS; no-op byte-identical; `--control leave-leaf` refused by joins (15,377/15,378). Step 2 (another cell) and new POIs remain open.
  - Step: P4

- [x] **M4.35 — `class_code` hypothesis: second-country or firmware-reader deepening**
  - Status: done · Owner: task/m4.35-classcode-reader · Critical: no · Pair: solo
  - Step: P3
  - Depends: M4.29
  - Goal: test M4.17's `class_code` hypothesis (class-pure codes in-sample, LORO fails globally) with evidence that can separate "road class code" from "numbering/page/region code".
  - Precheck: reproduce M4.17 Table B / M4.29 control counts on the pinned EU sample with the committed tools (`python3 tools/road_class_probe.py --selftest` passes); identify one concrete second-country or non-motorway control sample available per rule 11/12.
  - Scope: offline analysis only. Either (a) a second country/control set with OSM refs, or (b) firmware-side evidence for the `class_code` field reader if a VA is locatable without guessing. No RDSTM writer, no L4.
  - Input: EXP-2026-11-08-M4.17, EXP-2026-11-08-M4.29-r2, `tools/road_class_probe.py`, `tools/lctbl_records.py`, `docs/format/rdstm.md`; M4.17/M4.29 follow-up notes.
  - Done when: EXP reports whether the pure `class_code` values recur for the same semantic class in the control sample (with counts and a negative control), or locates/denies a firmware reader path with VAs/evidence; updates claims as `HYPOTHESIS`/`OBSERVED`/`RETRACTED` only with reproducible commands.
  - Stop: after two control samples or two signature families fail to separate class from identity/region, record the negative and stop; do not promote `class_code` to a class mapping.
  - Claims: C-3200–C-3209
  - Result: `docs/experiments/EXP-2026-11-21-M4.35-kind-code-second-country.md` (C-3200–C-3204). `class_code` is field 0 `kind code` = TMC location type `10000·class + 100·type + subtype` (first read so by M4.31, C-5961). New `tools/lctbl_kind.py` (`--selftest`) confirms it without OSM on both cards: US 2011 as the second country (303,023/303,023 records split), every resolvable reference obeys the class (1,667,631/1,667,631; permuted codes 36 %), and the `L1.x` subtype equals the road class shown by the road-number syntax in Czechia, Germany, UK and USA (7,831/7,852). It is a road class only for `L1.1`–`L1.4`; M4.17's `0x283c` is `L3.0`, a segment of any class, which is why LORO failed. Firmware: getter fn `0x003bbfe0` (`SDL_TMC_GetLocationCode`, EU2011) and its two callers named; the consumer after fn `0x004d197c` is not followed. C-1825 resolved.

- [x] **M4.31 — RDSTM link-class hints from pure `LCTBL001` class codes and link attributes**
  - Status: done · Owner: task/m4.31-rdstm-lctbl-class · Critical: no · Pair: solo
  - Result: EXP-2026-11-20-M4.31-tmc-road-type-link-class — `class_code` is the TMC location type (field 0, 247,089/247,089; `0x2775` = `L1.1` motorway). Through the location-code join (M4.16b/M4.16e) the record's road type predicts the level-2 section-2 class nibble `cls & 0xf`: modal accuracy 0.608 vs shuffled null max 0.382 on 158,445 records of 14 tables (positive control road identity 0.539 vs 0.400, negative `code & 1` 0.350 = null); `L1.1` → 1 (9 of 10 countries), `L1.2` → 4 (3 in FI/DK/SE), `L1.3` → 5, `L1.4` → 7. Generator hint (HYPOTHESIS): level-2 class 1 motorway / 4 primary / 5 secondary / 7 tertiary, the `fa_encode.CLASSES` level-2 column. `tools/rdstm_class_hint.py`. C-5960–C-5965; C-2971/C-2975 superseded.
  - Re-opened (rule 15, PO 2026-11-20): both `Unblock` routes have landed. M4.16b/M4.16e give the offline TMC record join (C-5400–C-5403), and M4.39 gives the route-link key `(parcel code, class & 0xf, entry word 3 & 0x1fff)` and reports that `LCTBL001` has no numeric key, name text only (C-5150–C-5156). Timebox one session: either join `LCTBL001` to links by name text through section 4 and report hit/null rates, or close this block as answered negatively by M4.39.
  - Step: P3
  - Blocker (history, resolved by M4.16b/M4.16e): no stable join key between `LCTBL001` records and RDSTM/routing links on available samples (LCTBL has no coord/country/mesh/parcel/link id; tile sec2 entries have no LCTBL ref; RDSTM001 C-884 TMC framing not reproduced offline, C-2304, and RDSTM001 is TMC not routing links, C-887).
  - Unblock: M4.16b/C-884 (offline RDSTM001 TMC extraction for a TMC-side record join) or a new scoped task establishing a decoded, stable LCTBL↔MAPAL tile sec2 routing-link identifier (footer/attrs/page join) with controls.
  - Result (history, superseded): EXP-2026-11-08-M4.31-rdstm-link-class-hints (negative/Stop; M4.17 Table B precheck reproduced; join-key candidates tested with controls; bounded within-LCTBL record-identity test shows attr/footer co-variation but not a routing-link attribute or generator hint). Claims C-2970–C-2979.
  - Depends: M4.17, M4.18
  - Goal: deepen M4.17's negative result toward the project goal (routable OSM
    roads). M4.17 found no general road-class field but observed
    motorway-pure/near-pure `class_code` values on joined numbered rows; use
    those as controlled hints and test whether they correlate with any
    decodable RDSTM/LCTBL link attribute, so M4.2/M5.3 get a narrower
    hypothesis than "class_code is the class".
  - Precheck: `python3 tools/road_class_probe.py --selftest` and
    `python3 tools/lctbl_records.py --selftest` (or their existing selftests)
    pass; reproduce M4.17's Table B counts for the pinned EU 2011 LCTBL sample
    from the M4.17 EXP commands on the same sample if available.
  - Scope: EU 2011 (and EU 2014 only as replication) pinned samples named in
    M4.17/M4.18; `LCTBL001` and the specific RDSTM/INTER fields already
    decoded. Excludes inventing a road-class encoding for generator output.
  - Input: `tools/road_class_probe.py`, `tools/lctbl_records.py`, M4.17 EXP
    C-1820–C-1828, M4.18 layout, M4.23/M4.24-26 restriction/connectivity
    findings where they touch link identity.
  - Done when: the EXP reports, with positive and negative controls, whether
    pure `class_code` groups co-vary with any tested RDSTM/LCTBL attribute at
    better-than-null rates; every claimed correlation states the join key and
    corpus size; and the result either yields a named, falsifiable generator
    hint (hypothesis) or records the tested attributes as negative with their
    controls.
  - Stop: if no stable join key exists between the LCTBL records and RDSTM
    links on the available samples, set `blocked` and name the missing join
    (do not guess by row order alone).
  - Claims: C-5960–C-5969 (was C-2970–C-2979; fresh block for this run)

- [x] **M4.46 — `tools/addre.py` misses the street name on shards whose name section starts `05 LL 00 ff`**
  - Status: done · Owner: task/m4.46-addre-tt05-names · Critical: no · Pair: solo
  - Depends: — (found by M4.39)
  - Goal: `addre.parse_record` recognises the 2011 `c0` name section only with `TT` = `0x03`/`0x04`; on `ADDRE005` (Germany) `TT` is `0x05` and it returns no name for all but 18 of the first 81,313 `c0` records, so every ADDRE name census built on it undercounts those shards (C-5156).
  - Precheck: `python3 tools/addre.py records $F/REFER001/ADDRE005.DAT.cmp --limit 20` prints `name=` empty on `c0` rows; `python3 tools/route_link_join.py --selftest` passes (its `street_name` reads the same records by the `TT LL 00 ff` rule).
  - Scope: `tools/addre.py` `parse_record` name detection and its selftest; census of `TT` per shard over the 33 EU2011 ADDRE files (count only). No ADDRE writer change.
  - Input: EXP-2026-11-19-M4.39-route-link-id (C-5156), `docs/format/refer.md` §Address records, `tools/route_link_join.py` `street_name`.
  - Done when: `TT` per shard is tabulated in `refer.md`, `addre.py` returns a name for every `c0` record on ≥ 3 shards with different `TT` (positive), and still none on `c8` (negative).
  - Stop: if a shard's name section does not follow `TT LL 00 ff`, record the shard and its first 16 bytes and stop.
  - Claims: C-5157–C-5159
  - Result: EXP-2026-11-20-M4.46-addre-tt05-names (C-5157–C-5159). The `c0` name section sits at byte `4 + 2*rec[2] + 2*rec[3]` in 4,610,363/4,610,363 `c0` records of the 33 EU2011 shards (0 of 7,424,226 `c8`); `addre.parse_record` now places it there and names every `c0`, no `c8`. `TT` per record: `0x03` 2,531 / `0x04` 1,332,147 / `0x05` 3,275,685, constant in 26 shards, mixed in 7 (table in `refer.md`). The old `TT` 3/4 rule (`names --legacy`) missed 3,275,685 names (71.0 %) on 14 shards. New `addre.py names` census; `_zlib_at` no longer copies the file tail per stream (large shards now read in minutes).

- [x] **M4.41 — Differential decoding: the same tile in 2011, 2014 and 2016**
  - Status: done · Owner: task/m4.41-diff-years · Critical: no · Pair: solo
  - Depends: — (three EU images are on the allowed host)
  - Goal: three editions of the same map are the cheapest oracle for field meaning. A tile where one road was added between 2011 and 2014 shows which bytes of section 1, section 2, section 4 and `LEV3456R` belong to one road. No firmware and no hardware.
  - Precheck: `python3 tools/fetch_image.py --image EU2014 -o PATH` and `--image EU2016` verify; `python3 tools/diff_years.py -h` runs.
  - Scope: all `MAPAL001/B*R.DAT` of the three editions: per tile, per section, size and SHA-256; then the 20 tiles with the smallest non-zero section-1 change. For each: which section-1 records were added/removed, and the byte ranges that changed in sections 2 and 4. No interpretation beyond "changes together with".
  - Input: `tools/diff_years.py`, `tools/tile_diff.py`, `tools/ze0-viewer` (section split), `docs/research/image-versions.md`.
  - Hints: sort by edit distance, not by size change — a renamed street changes section 4 only, a new roundabout changes all three. A tile whose section 1 is identical and section 2 differs is a routing-only edit (turn restriction, one-way): those are the pure samples M4.23/M4.3 never had. Record how many bytes of section 2 change per added section-1 road: a constant is the record size.
  - Done when: an EXP with the per-section change census for all tiles (counts) and the 20-tile table; at least three "one variable" pairs (one added road; one renamed road; one routing-only change) named by tile and offset for M4.40, M4.36 and the section-4 reader (M3.6; **M4.21**, the section-4 writer, is done and archived in `todo-history-2026-11-09.md`) to use.
  - Stop: if fewer than three clean pairs exist, publish the census and say so.
  - Claims: C-4590–C-4599
  - Result: EXP-2026-11-19-M4.41-diff-years (C-4590–C-4599): `tools/diff_years_tiles.py` gives the per-section `kept/changed/added/removed` census for 45 tiles × 2 pairs (2011→2014 sec1 606622/1402020/135997/187413; 2014→2016 sec1 755251/1308596/68171/80792) with the 20-tile tables, and names section-4 rename records (e.g. `B48R070R` `CRICCLETH;`→`CRICCIETH;`) and the `B60R060R` added-road sample. `Stop:` applies — the editions move all three sections together, so fewer than three clean one-variable pairs exist; the census is the result.

- [x] **M5.15 — `build.py` writes a card: factory image + OSM → card image → checks**
  - Status: done · Owner: task/m5.15-build-py-card · Critical: yes
  - Step: tooling
  - Depends: M5.11 (one tile end to end); grows with each writer (M5.4–M5.7, H11 rows)
  - Goal: the one command Marek described: take a factory card image, drop
    the map data the profile replaces, write OSM-generated files in the
    confirmed formats, keep the verbatim-copy set (M3.17), rebuild
    `DRSTR001`/`MMAIN001`/`CMP.LST`/`.ind`, pack the card image, then run the
    checks. `build.py` today only dry-runs (exit 3 without `--dry-run`).
  - Input: `tools/build.py` + profiles (M7.4 schema v2), `osm_ingest.py`,
    `mesh_split.py`, `tilewriter.py`, the M5.6 rebuild, `mkcard.py` (with
    M5.12b) or `imgpatch.py` (M5.13); checks `cardcheck.py`, `l2check.py`,
    `realcheck.py`, `l3check.py --card` (M9.12/M9.16) and, once F4 exists,
    the M8.E4 emulator run.
  - Done when: `build.py --profile profiles/dolnoslaskie-test.json --from-image
    IMG --osm EXTRACT -o out.img` writes an image and a report listing, per
    file family, *generated / copied / not yet generated (factory kept)*,
    then each check's verdict; it refuses to report success if any check
    fails. First milestone: one generated tile (= M5.11); every new writer
    adds its family. OSM extracts stay outside the repo (rule 12).
  - Claims: C-5360–C-5369 (was C-2280–C-2289; fresh block for this run)
  - Result: EXP-2026-11-20-M5.15-build-py-card. `build.py` write mode (one tile, one section-1 directory): EU 2011 + `m5.37-splice.osm` → `out.img` `b88a31f4…` (= M5.11 byte for byte), 24 families (1 generated, 4 rebuilt, 7 not yet generated, 12 copied), 8 checks PASS incl. L3 map-code ACCEPT, 5 gates cannot-verify-offline, ladder P0; failures exit 1 and remove the image; several tiles / added files exit 3.

- [x] **M5.26 — Whole-POINT-pair regeneration for OSM name sets (beyond in-place slot budget)**
  - Status: done · Owner: task/m5.26-point-pair-regen · Critical: yes
  - Depends: M1.13, M1.16, M5.21
  - Goal: make mass POI/name generation feasible for the OSM compiler. M5.21
    showed 98.6 % of edited POINT pages abut their slot and in-place edits fit
    only 13,749 / 5,891,589 names at 4 % headroom (152,085 at 0 %), which blocks
    real Dolnośląskie/Poland name sets if the compiler only patches pages.
  - Precheck: `python3 tools/slot_budget.py --selftest` and
    `python3 tools/factory_zlib.py --selftest`; confirm M1.13's pinned encoder
    (stock zlib level 6, memLevel 8, wbits 15, default strategy) is the
    default path used for regenerated inner streams.
  - Scope: `REFER001/POINT*.DAT.cmp/.ind` pair regeneration for a supplied name
    set (synthetic fixture first, then a real sample). Out of scope: changing
    the on-disk record grammar (M4.x), tile geometry, or forcing slot-fit on
    abutting factory pages.
  - Input: M1.13 encoder result, M1.16 shared codec (when landed; otherwise
    current helpers), M5.21 refusal/budget report format, a synthetic POINT
    fixture with known `NAME@` records and a factory-like pair layout.
  - Done when: a tool/entrypoint (name stated in the PR) regenerates inner zlib
    pages and rebuilds a `.cmp/.ind` pair so that `cmpind.py` decodes it,
    every requested synthetic name is present with `@`, page/offset tables stay
    consistent, the result is refused with a clear error when a record/table
    constraint is violated, and a control proves an unchanged name set can be
    regenerated without inventing record bytes. L2/round-trip checks that apply
    to synthetic fixtures pass; a real-image run is reported in the EXP (rule 11).
  - Stop: if regenerating pages requires unknown POINT page-table/record fields,
    record the exact field and open/block on the specific M4/M3 task instead of
    guessing offsets.
  - Claims: C-2950–C-2959
  - Result: EXP-2026-11-19-M5.26-point-pair-regen (C-2950–C-2957). New tool `tools/point_pair_regen.py` (`scan`/`regen`/`verify`/`locator`/`summarize`). POINT pages sit in chains described by chain tables (`u16 per_page, u16 0, n × (start_w, comp_w, inner_w)`, three per file); `regen` re-packs a whole chain, rewrites its table and rebuilds the pair; the no-op control with stock zlib 1.3.1 is byte-identical on 44/44 EU+US pairs; EU POINT010 takes 1,000 names (+2 B each, page 0 +176 B past its own slot), all with `@`, `cmpind` decodes it. Limit: a chain cannot move — its locator is UNKNOWN (C-2955) and chain slack is 24–248 B, so real-name sets of 10–100 names already overflow most chains → M4.47.

- [x] **M5.27 — Finish M5.12c uncompressed-file scan and reconcile EXP/TODO status**
  - Status: done · Owner: task/m5.27-m5.12c-scan · Critical: no
  - Step: P4
  - Note (H51, 2026-11-11): unowned for three days and it gates what Marek should expect on screen for S2 (M6.6). It is a scan, not research: `python3 tools/poi_copies.py` on the US tree; the full US image is on the allowed host (`fetch_image.py --image US`).
  - Depends: M5.12c
  - Goal: close the integrity gap left by M5.12c: commit `95a4b42` and TODO mark
    M5.12c blocked because the uncompressed-files exact scan never finished and
    the done-when is unmet, while `EXP-2026-11-08-M5.12c-poi-copies.md` still
    carries `Status: done` in its header/body.
  - Precheck: `python3 tools/fetch_image.py --image US --verify <path>` (or an
    existing verified US image path); `python3 tools/poi_copies.py --selftest`.
    If the US image is unavailable in the session, fetch/verify it (rule 11)
    or record the exact unavailability and stop.
  - Scope: the uncompressed files of the US tree named in M5.12c Method 3 and
    the M5.12c EXP/TODO metadata. No new rename edits to the image.
  - Input: US 2011 image/tree, `tools/poi_copies.py`, M5.12c target names and
    the existing EXP record.
  - Done when: the uncompressed-file exact scan completes and the EXP records a
    table of hits (file, offset, encoding, name, `@` context) or an explicit
    empty result; `EXP-2026-11-08-M5.12c-poi-copies.md` no longer claims
    `Status: done` for an unfinished done-when (status/body reconciled, with the
    reason stated); and TODO M5.12c is either moved to `done` with the completed
    evidence or kept `blocked` with the narrowed remaining blocker.
  - Stop: if the scan cannot run to completion in the available environment,
    keep M5.12c `blocked`, record the partial scope counted, and do not mark the
    EXP done.
  - Unblock: M5.12c
  - Claims: C-2960–C-2969
  - Result: EXP-2026-11-20-M5.27-m5.12c-scan. Complete: 132 files,
    2,966,260,099 B, 6,964,109 zlib streams inflated (97 min, after a
    `poi_copies.py` fix that skips header candidates inside an inflated
    stream). 175 Latin-1 hits (155 street/feature names such as `CRAB ORCHARD
    RD`, 20 bare `CRAB ORCHARD` tile labels), none followed by `@`; 0 hits for
    `HANA HEALTH*`, `GODFATHER'S`, `BLIMPIE`. The M5.12c EXP header is
    corrected in place and M5.12c is done. Claims C-2960–C-2963.

- [x] **M5.33 — Make M5.29 synthetic scaffold/tile coherent for `cardcheck`/applicable `l2check` (honest gates)**
  - Status: done · Owner: task/m5.33-synthetic-scaffold · Critical: yes · Pair: required
  - Depends: M5.29
  - Goal: close the synthetic-path validator failures reported by M5.29 so the no-vendor milestone can produce actionable L1/L2 gate evidence on a synthetic tree, while keeping factory-backed acceptance and firmware acceptance separate and honest (rule 13).
  - Precheck: `python3 tools/one_tile_pipeline.py --selftest` passes; reproduce `one_tile_pipeline.py --out <tmp> --cell B48R058R` then `cardcheck.py --root <tmp> --partial --ignore-dump-artifacts --fast` and `l2check.py --root <tmp> --partial --no-golden --no-cmp --tiles B48R058R.DAT` failures as recorded in EXP-2026-11-09-M5.29 (MMAIN/section-level alignment; `ze0_mutate`/`clarion_tile.read_tile` `struct.error` on synthetic scaffold tile buffer, e.g. `B30R060R.DAT`). Pass the `<cell>.DAT` file name: `--tiles B48R058R` (a bare cell name) matches **0** tiles and still prints `RESULT: PASS` (C-3566).
  - Scope: `tools/one_tile_pipeline.py` synthetic scaffold/helpers and, only if required by the root cause, minimal fixes in `tools/rebuild_manifests.py`, `tools/tilewriter.py`, or `tools/ze0-viewer` parse assumptions used by `l2check`/`ze0_mutate` — name exact changed functions/files in PR. Do not claim factory parity, do not fetch/commit vendor bytes, do not weaken gates to fake PASS.
  - Input: EXP-2026-11-09-M5.29-one-tile-pipeline, `tools/one_tile_pipeline.py`, `tools/rebuild_manifests.py`, `tools/tilewriter.py`, `tools/l2check.py`, `tools/cardcheck.py`, `tools/ze0-viewer/ze0_mutate.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py`.
  - Done when: on the synthetic M5.29 path, `cardcheck` and applicable `l2check` gates either `PASS` with a coherent synthetic scaffold/MMAIN/tile set or are reported as `NOT-APPLICABLE`/`CANNOT-VERIFY-OFFLINE` only for gates that genuinely cannot apply to synthetic/no-vendor trees — never because of a malformed scaffold. EXP records failing checks before/after, commands, hashes of generated synthetic artifacts, and states `mapping=provisional-v0`, rule 13, L3/L4/L5 unknown.
  - Stop: if making the synthetic scaffold validator-coherent requires factory tile bytes or firmware-confirmed structure not available offline, record the exact dependency and block that specific gate as `CANNOT-VERIFY-OFFLINE` with evidence; do not invent bytes.
  - Claims: C-3420–C-3429
  - Result: EXP-2026-11-19-M5.33-synthetic-scaffold — synthetic tree now `cardcheck` PASS (headers 4/4, MMAIN 11/11 rows) and targeted `l2check --tiles B48R058R.DAT` PASS (`tiles=1`); root cause: tilewriter synthetic mode wrote the X08-03-00 header, re-authored as ZE0 X08-02-00 by new `tools/ze0_tile_header.py` (46/46 EU 2011 headers rebuilt exactly); `section4` stays CANNOT-VERIFY-OFFLINE, rule 13. C-3420–C-3426.

- [x] **M5.32 — Resolve M5.12c's 5 unfit POI pages with the M5.21 slot-budget strategy**
  - Status: done · Owner: task/m5.32-unfit-poi-pages · Critical: yes · Pair: required
  - Step: P4
  - Depends: M5.21, M5.27
  - Goal: close the remaining 5 unfit POI pages from M5.12c (131/136 edited; 5 left per M5.12c S4) using a slot-safe strategy, now that M1.13 establishes stock zlib L6/m8 as the factory-equivalent encoder.
  - Precheck: reproduce the S4 unfit pages with `tools/mutate_refer_poi.py`/`tools/slot_budget.py` and stock zlib L6/m8; confirm M5.27 has reconciled M5.12c EXP/TODO status or record the dependency explicitly.
  - Scope: the 5 named pages/records only. Allowed outcomes: fit with a slot-safe repack/refit strategy that never overruns a neighbour, or explicitly refuse with measured slot/candidate sizes and a documented follow-up (page relocation/split). No silent overrun; no whole-POI-file rewrite unless every changed range is proven and cardcheck passes.
  - Input: EXP-2026-11-08-M5.12c-poi-copies, EXP-2026-11-08-M1.13-factory-encoder, EXP-2026-11-08-M5.21-slot-budget, `tools/slot_budget.py`, `tools/mutate_refer_poi.py`, `tools/factory_zlib.py`.
  - Done when: each of the 5 records is either edited on a `cardcheck`-passing image with diff ranges confined to the affected page/slot envelope (reported) or listed as refused with slot/candidate sizes and a concrete follow-up; EXP gives per-page before/after sizes and hashes.
  - Stop: if no slot-safe same-page strategy fits after the M5.21/M1.13 encoder search, stop with `blocked` or `open` follow-up for page relocation; do not pad over non-zero bytes or overwrite the next page.
  - Claims: C-3190–C-3199
  - Result: EXP-2026-11-20-M5.32-unfit-poi-pages. All 5 records edited (4 × `RAB ORCHARD` → `OSM2 RAB 01` on `POINT006` `0x12d94cc0`, 1 × `HARDEE'S` → `OSM2 H01` on `POINT008` `0x152e4a08`). With stock zlib L6/m8 the pages grow by only 5 / 7 B (M5.12c's 250 / 72 B was zlib-ng); they abut their neighbours, so the per-page M5.21 rule refuses, and the chain-level `point_pair_regen.py regen` fits them in the pooled chain slack (196 / 132 B left), with no relocation. Inside the `.DAT` nothing changed outside the chain slot, table and base-reference length (`outside 0`); the US card passes `cardcheck` (RESULT: PASS) and `imgpatch --check-diff` (outside 0, only the 4 files). L3 `point_locator_l3.py` (US2011 `0x00426480`) ACCEPTs the edited and shifted pages. Fix: `regen` now rewrites the M4.47 base reference's length word, which it had left stale (C-3193). Claims C-3190–C-3194.

- [x] **M5.36 — L2 golden for the road-class table: an OSM class written to a tile must decode back to the same class**
  - Status: done · Owner: task/m5.36-tile-class-roundtrip · Critical: yes · Pair: required
  - Step: P2
  - Depends: M5.16 not required; M5.4 (tile splice, done), M5.28 (`roadclass_v0`, done), H41 (per-feature matrix, open — this task supplies the L2 row it reports, not the reporter)
  - Goal: `roadclass_v0` maps 17 OSM highway classes to a provisional Clarion class, but nothing checks the *round trip* at L2: no test asserts that the class emitted into a tile's road records decodes back to the same OSM class under `l2check`/`clarion_tile`. A wrong table can ship a road drawn as a motorway and every existing gate stays green. This is the cheapest map-quality check that can fail loudly.
  - Precheck: `python3 tools/roadclass_v0.py --selftest` passes and `python3 tools/tilewriter.py --selftest` is 68/68; `python3 tools/l2check.py --help | grep -- --semantic-tiles` exists (the hook this task extends). Confirm no current check compares a decoded class to the emitted class: `grep -rn 'class_code\\|road_class\\|cls_hi' tools/l2check.py tools/ze0-viewer/ze0_mutate.py` prints only writer-side fields.
  - Scope: `tools/l2check.py` (one new check `tile_class_roundtrip`) and one synthetic no-vendor fixture in `tools/l1l2_fixtures.py`: build a tile with a known class table via `tilewriter`, decode it, and compare per-road class to the emitted class. The real-image variant runs on the M5.4 `B48R058R` splice. No format change, no new class value; a mismatch is a failed check, not an `UNMAPPED` excuse.
  - Input: `tools/roadclass_v0.py` (the `mapping=provisional-v0` table), `tools/tilewriter.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py` (the decoded class field), M5.4 EXP, H41's matrix shape.
  - Hints: if the decoded field is not yet known (M5.23), compare at the level the writer controls and state the field in the EXP; do not invent a class semantics. Keep it a separate check name so H41 can report `L2 roadclass` as its own row. This does not confirm the class is *correct* on the car — only that the pipeline does not corrupt it (rule 13 stays open).
  - Done when: `python3 tools/l2check.py --root <synthetic> --partial --no-golden --no-cmp --class-tiles B48R058R.DAT` reports the `[tile_class_roundtrip]` row PASS on the fixture and `FAIL` when the fixture's emitted class is mutated by one value (`--class-tiles` is the wiring flag, `--semantic-tiles` runs the separate `check_tile_semantic`; the `.DAT` form is mandatory per M5.39/C-3566); the real `B48R058R` splice reports its class rows; `python3 tools/selftest.py` passes; EXP records the per-class table and the negative control.
  - Stop: if the tile record does not carry a recoverable class for any road (M5.23 not decoded), record `NOT_APPLICABLE — class field not readable` with the field location, and do not fake a pass.
  - Falsifier: the check passes on a tile whose emitted class was deliberately changed to a different value, or a class that decodes differently still reports PASS.
  - Claims: C-5790–C-5799
  - Result: EXP-2026-11-20-M5.36-tile-class-roundtrip — `tools/tile_class_roundtrip.py` + `l2check --class-tiles`: PASS on the synthetic fixture (2 parcels, 3 shapes; one-value mutant FAIL by name) and on the real `B48R058R` splice (`match=6 fail=0`, 47,650 factory records untouched); dump→check on the untouched factory tile 47,656/47,656; a tile with no emitted map reports a `decoded` census, never PASS. Level-1 class field `w[p+2] >> 12` recoverable for every road, so the Stop does not apply (C-5790–C-5792).

- [x] **M5.39 — `l2check --tiles` accepts a bare cell name, matches 0 tiles and prints `RESULT: PASS`**
  - Status: done · Owner: task/m5.39-l2check-bare-cell · Critical: no · Pair: solo
  - Depends: — (`tools/l2check.py` is on `main`; no other task's block is needed)
  - Goal: C-3566 records the footgun without a task: every caller that writes `--tiles B48R058R` (M5.33's Precheck did, until QA 2026-11-17 fixed that line) gets `tiles=0` and `RESULT: PASS`, so a broken tile reads as a passing gate. This is the L2 signal M5.34/M5.30/M5.11 depend on, not a record repair.
  - Precheck: on the factory root `python3 tools/l2check.py --root /home/marek/projekty/leafre-work/m5.29-factory-root --partial --no-golden --no-cmp --tiles B48R058R` prints `[tile_roundtrip] OK (tiles=0; preserved=0)` and `RESULT: PASS`; the same command with `--tiles B48R058R.DAT` prints `tiles=1`.
  - Scope: `tools/l2check.py` only: a `--tiles`/`--semantic-tiles` value that names no file present on the card is a usage error (exit 2) or, under a new `--require-tiles`, a `FAIL`; a bare cell name (`B48R058R`) is named in the message with the `.DAT` form to use; a requested name that resolves to a file is unchanged. Do not change what the tile checks assert.
  - Input: `tools/l2check.py` (`--tiles`, `--semantic-tiles`, the `tiles=` count), C-3566, EXP-2026-11-17-M5.34-parcel (Follow-ups), M5.33's Precheck.
  - Done when: `python3 tools/l2check.py --root <factory-root> --partial --no-golden --no-cmp --tiles B48R058R` exits non-zero and names `B48R058R.DAT`; with `--tiles B48R058R.DAT` it still prints `tiles=1` and `RESULT: PASS`; `--selftest` covers both; `python3 tools/selftest.py --only l2check` and the L1/L2 CI job stay green with a fixture that needs no vendor data.
  - Stop: if the tile check cannot run without a vendor root, land only the name-vs-file rejection (exit 2) and record the vendor-root limitation; do not invent a fixture.
  - Claims: C-4290–C-4299
  - Result: EXP-2026-11-19-M5.39-l2check-bare-cell — on the EU 2011 factory root (480 files) `--tiles B48R058R` went from `tiles=0` + `RESULT: PASS` (exit 0) to exit 2 naming `B48R058R.DAT`; `--tiles B48R058R.DAT` unchanged (`tiles=1`, PASS); new vendor-free `--selftest`. C-4290–C-4295.

- [x] **M5.41 — One expected-change-set for the one-tile run: `changed_set_expected` and the gate disagree on `DRSTR001.DAT`**
  - Status: done · Owner: task/m5.41-expected-changes · Critical: no · Pair: required
  - Depends: M5.34 (done — the run and the gate it reports)
  - Goal: `one_tile_pipeline.build_factory_out` writes `changed_set_expected = ["MAPAL001/<cell>.DAT"]` (`tools/one_tile_pipeline.py:1250`) while no other place defines what a correct run is allowed to change: the gate's manifest allowlist is a literal at `:1399` and is never exported, and the non-parcel path fills `changed_set` from `counts.rebuilt_files` (`:663`, `:1367`). On the M5.34 run the two disagree (`changed_set_expected` excludes `DRSTR001.DAT`, the file that does change and that the gate accepts), so a reader or a future card gate that trusts `expected` would read the correct run as wrong. Two definitions of one set in one module is the coupling defect; the fix is one function.
  - Precheck: `python3 -c "import json;d=json.load(open('/home/marek/projekty/leafre-work/m5.34/nav-report.json'));print(d['changed_set_expected'], [x['path'] for x in d['tree_diff']['differing_files']])"` prints `['MAPAL001/B48R058R.DAT']` against `['DRSTR001.DAT', 'MAPAL001/B48R058R.DAT']`.
  - Scope: `tools/one_tile_pipeline.py` only: one `expected_changes(cell, rebuilt)` helper returning the **narrow 2-path** `expected` set (tile + `DRSTR001.DAT`, the Done-when literal — not `{tile} ∪ rebuilt_files`, which is 198 on M5.34) plus two separate sets: `allowed_but_unchanged` (`MMAIN001.DAT`, `CMP.LST`, the 194 `.ind` = 196 paths) and `allowed_manifests` (the gate's 3-name allowlist, which must NOT grow with `rebuilt_files`). Used by `build_factory_out` and `build_synthetic_out`; `one_tile_gate`'s `manifests` argument keeps the 3-name allowlist. `report.json` keeps `changed_set_expected`, `changed_set_actual`, `allowed_but_unchanged`, `allowed_manifests` and `expected_superset_of_actual`; the selftest asserts `expected ⊇ actual`, that an out-only file still leaves `unexpected_differences` non-empty, and that a content-differing rebuilt `.ind` still FAILs the narrow gate. No change to the gate's PASS conditions.
  - Input: `tools/one_tile_pipeline.py` (`:663`, `:1250`, `:1367`, `:1395-1410`, `one_tile_gate` at `:1119`), EXP-2026-11-17-M5.34-parcel (`tree_diff`), C-3563.
  - Hints: do not fold `MMAIN001.DAT`/`CMP.LST` in unconditionally — the M5.34 run re-emits them byte-identically and they are *allowed*, not *expected*; keep "allowed" and "expected" as two sets if the export needs both.
  - Done when: on the M5.34 factory run `changed_set_expected` equals `{MAPAL001/B48R058R.DAT, DRSTR001.DAT}` and still satisfies `expected ⊇ actual`; `python3 tools/one_tile_pipeline.py --selftest` passes and covers (a) a report whose actual set is the expected set, (b) an extra out-only file (B2) still FAILs, (c) a run that changes only the tile leaves `DRSTR001.DAT` out of `actual` without failing `expected ⊇ actual`.
  - Stop: if a second caller depends on `changed_set_expected` meaning exactly one path, name it in the EXP and keep both keys (`changed_set_tile`, `changed_set_expected`); do not delete a field another task's Done-when cites.
  - Falsifier: a fixture where `actual` is a strict subset of `expected` still reports `tile_plus_manifests_only: false`, or a gate PASS survives an unexpected file.
  - Result: `expected_changes(cell, rebuilt)` returns `expected = {MAPAL001/B48R058R.DAT, DRSTR001.DAT}`, `allowed_but_unchanged` (196 = 194 `.ind` + `CMP.LST` + `MMAIN001.DAT`) and the narrow `allowed_manifests`; on the M5.34 inputs `changed_set_expected == changed_set_actual` and `expected_superset_of_actual: true`, rebuilt/differing/union `197/2/198`, tile byte-identical (`293990518 B` / `b746427c…34c2ef`); `one_tile_pipeline --selftest` 106 ok / 0 failure, `selftest.py --only one_tile_pipeline` `passed=1 failed=0` — EXP-2026-11-19-M5.41-expected
  - Claims: C-4600–C-4609

- [x] **M5.42 — Records overtaken by a later merge: a TEMPLATE section, plus four concrete corrections**
  - Status: done · Owner: task/m5.42-overtaken-records · Critical: no · Pair: solo
  - Depends: — (all four records are merged; this is text)
  - Goal: a record that a later commit overtook still reads as current, and `claims_check` cannot see prose. Four instances from the 24h window, each with the file it lives in: (1) `docs/research/claims.md` C-1240 ends "so M8.A2 stays `blocked`" although #217 closed it (the row's own status column already says `BLOCKED (done-when access-list clause)` and the clause was withdrawn); (2) `docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` Status bullet says "Task status is `blocked`, not `done`" and its own §Verdict line says the same; (3) the same EXP's **Status** header (lines 5-7) and its `Notes left for the navigator` last bullet repeat it; (4) C-3563 and C-3564 say `DRSTR001.DAT` changed because "the tile's on-disk size changed" — the measured diff is 7 bytes: the `MAPAL001` directory entry's `value` word (`0xd1e00400 → 0xd2274b76`, +0x474776 = the +4,671,350 B appended tail, i.e. the new structure offset) *and* the `B48R058R.DAT` entry's size word (`0x113ea900 → 0x1185f076`), i.e. offset **and** size, so the reader learns where the new tail starts as well as how big the tile is.
  - Precheck: `grep -n 'M8.A2 stays' docs/research/claims.md` and `grep -n 'Task status is .blocked' docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` each print a line; `cmp -l ~/projekty/leafre-work/m5.29-factory-root/DRSTR001.DAT ~/projekty/leafre-work/m5.34/nav-out/DRSTR001.DAT | wc -l` prints `7`.
  - Scope: `docs/experiments/TEMPLATE.md` gains one section, **"Overtaken by a later commit"** — a bullet list `claim/EXP line | overtaking commit | what it now reads as`, required whenever a later merge changes a status, a count or a limit the record cites, with the same "quote the command" rule as everywhere else; the four corrections above as edits in place (C-1240, the M8.A2 Status/Verdict/navigator note, C-3563, C-3564) each naming the overtaking commit (`280cd74`, `f5df583`). No new claim rows, no number changes beyond the two measured byte offsets.
  - Input: `docs/research/claims.md` C-1240/C-3563/C-3564, `docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` (Status, Verdict, Notes), EXP-2026-11-17-M5.34-parcel §Observations `tree_diff` block, `git log -1 280cd74`, `docs/experiments/TEMPLATE.md`.
  - Hints: keep "observations" and "corrections" apart in the M8.A2 EXP — the Status header is metadata, the §Verdict row is the evidence table; edit both to the same sentence. Do not re-run anything; every number in the four edits is already in the EXP or in the command above.
  - Done when: the TEMPLATE has the new section and `python3 tools/claims_check.py --strict --count-check` still prints `0 mismatches`; `grep -c 'M8.A2 stays' docs/research/claims.md` prints `0`; the M8.A2 EXP Status and Verdict say `done` with the `280cd74` merge named; C-3563/C-3564 name the 7 bytes (size word + offset word) instead of "the on-disk size"; `python3 tools/todo_check.py` passes.
  - Stop: if a correction would change a VERIFIED claim's meaning (not just its stale tail), stop and write a `Supersedes:` row instead of editing — that is a new claim, not a correction.
  - Falsifier: a record still says `blocked`/`stays blocked` for M8.A2, or C-3563 still attributes both changed words to the size alone.
  - Claims: C-5170–C-5179 (was none yet; fresh block for this run)
  - Result: EXP `docs/experiments/EXP-2026-11-19-M5.42-overtaken-records.md`. `TEMPLATE.md` gains **"Overtaken by a later commit"**; C-1240 and the M8.A2 re-probe EXP (Status, §Verdict, navigator note, Reproduction `--version 8.2.7`) now say `done` naming `280cd74` (#217) and `f5df583` (#219); C-3563/C-3564 name the 7 DRSTR bytes: the `B48R058R.DAT` size word `0x113ea900 → 0x1185f076` (3 B) and the `MAPAL001` word `0xd1e00400 → 0xd2274b76` (4 B), which the factory DRSTR (`2b7f2fb8…`) shows is the **recursive subtree total** (46 children sum to 3,521,119,232 B, C-036), not a structure offset as the task text guessed; `grep -c 'M8.A2 stays'` 0, `claims_check --strict --count-check` 0 mismatches, `todo_check` OK. No new claim rows.

- [x] **M5.44 — Splice level-2 directories: a second detail level, on a tile that owns them**
  - Status: done · Owner: task/m5.44-level2-splice · Critical: yes · Pair: required
  - Depends: M5.4 (level-1 splice, done), M5.34 (factory-backed run, done), `tilewriter` accepts `--level 2`
  - Goal: only level-1 directories have ever been spliced, so the highest card rung that exists carries major roads at 1°×2/3° directory resolution and no detail below it. `B48R058R` does own level-2 directories (4 of them, all `0x2046` — see Precheck), so the finer level is reachable with the same container mechanics on a tile L2 already writes; this is the next map-content step before the card rung (M5.30). It also exposes the level-2 geometry model, which no test covers today.
  - Precheck: two commands, and the second is the finding. (a) `python3 tools/parcel_census.py ~/projekty/leafre-work/m5.29-factory-root/MAPAL001/B48R058R.DAT --sections 1 --levels 2` prints 4 directories, all kind `0x2046` / class `spliceable`, at `(72,936)`, `(72,940)`, `(76,936)`, `(76,940)`, each with a 1.0°×0.667° bbox. (b) `python3 -c "import sys;sys.path[:0]=['tools/ze0-viewer/tools_ze0','tools'];import clarion_bg;print(clarion_bg.parcel_geo(2,76,940,0,0), clarion_bg.parcel_geo(2,76,940,31,31))"` returns lower-left `16.0,50.66667` with a `0.125×0.0833` parcel, so the 32×32 grid spans **4.0°×2.667°** — four times the `directory_bbox(2,76,940)` extent. The two checked-in functions disagree on what a level-2 directory is; `parcel_census --selftest` only asserts the level-1 span.
  - Scope: (1) pin the level-2 directory grid from the factory tile itself — the slot-tag mesh of the 4 level-2 directories — and make `parcel_census.directory_bbox`/`clarion_bg.parcel_geo` agree at level 2 or state which one the directory header follows (one paragraph in `docs/format/map-tiles.md`); (2) the run: route the Dolnośląskie geometry into one level-2 directory and record `cardcheck`, targeted `l2check` (`tiles=1`), `changed_sections == [1]`, exactly one level-2 directory changed, tile size/SHA under stock zlib. If the pipeline lacks a `--level` pass-through, add the one argument (not a second pipeline). New EXP `EXP-<date>-M5.44-level2`; do not append to the M5.34 record.
  - Input: EXP-2026-11-17-M5.34-parcel (the run and the gate), `tools/parcel_census.py` (`directory_bbox`), `tools/ze0-viewer/tools_ze0/clarion_bg.py` (`LEVELS`, `parcel_geo`, `MESH_W/H`), `tools/tilewriter.py` (`--level`, `ways_to_runs`, `parcel_of` at level 2), `profiles/dolnoslaskie-test.*`, the factory root and the Geofabrik extract the M5.34 EXP names.
  - Hints: `tilewriter.parcel_of(16.5, 51.0, 2)` returns directory `(76,940)` with parcel `(4,4)`, so the directory identity is shared with level 1 and only the sub-mesh differs — but `parcel_geo(2, 76, 940, …)` then walks to `19.875,53.25`, i.e. 4× outside the box the census prints for the same directory. Settle that before a splice; a splice on the wrong grid writes road geometry into the wrong place and every L2 check still passes (it compares the writer to itself). `--parcel Y,X` still names the directory.
  - Done when: the level-2 geometry disagreement is resolved in the tools and `parcel_census --selftest` asserts the level-2 span (red on the old 4× value); a factory-backed level-2 run completes with `cardcheck` PASS, targeted `l2check` `tiles=1` PASS, `changed_sections=[1]`, exactly one level-2 directory changed, and the tile SHA/size in the EXP; a negative control (a node outside the chosen level-2 directory) refuses before any write; `python3 tools/selftest.py --only parcel_census --only tilewriter --only one_tile_pipeline` green.
  - Stop: if the level-2 slot tags do not yield a consistent 8×8-or-32×32 grid, record the tag table and block on the grid question as a format task (M4-level), not on a gate relaxation.
  - Falsifier: a section other than 1 changes, a second directory changes, or the gate PASSes a tile whose level-2 record does not decode back at the grid the census prints.
  - Claims: C-4450–C-4459
  - Result: EXP `docs/experiments/EXP-2026-11-18-M5.44-level2.md`. `parcel_census.directory_bbox(2,76,940)` / `--selftest` (`level-2 directory spans 4 deg lon x 8/3 deg lat`) fix the level-2 directory at 4°×8/3° over a 32×32 parcel grid (old value was 1/4 size); `python3.13 tools/one_tile_pipeline.py … --parcel 76,940 --level 2 … --osm-bbox 16.40,51.10,16.45,51.13 --clip` exits 0 with `cardcheck RESULT: PASS`, targeted `l2check` `tiles=1` PASS, `changed_sections=[1]`, `changed_directories=[(2,76,940)]` (`only_parcel_directory_changed=true`), tile 289,458,162 B SHA-256 `b4724f3723b21fa0c531094b6f1dd1941eff464e4674de8930617ac0aa34fdb0` (+138,994 B over the 289,319,168 B factory tile); the negative control leaves the parcel and exits 2 with no `--out`.

- [x] **M5.47 — M5.30's fit census: does one changed tile fit an existing cluster chain before anyone writes it?**
  - Status: done · Owner: task/m5.47-fit-census · Critical: yes · Pair: required
  - Depends: M5.29 (done — the changed tile and rebuilt manifests), M5.45 (done — the append/in-place/unchanged semantics the fit question needs)
  - Goal: M5.30 is the last P0 rung and its `Stop:` is "if changed tile/manifests cannot fit existing chains and relocate/reconcile widens diff beyond changed files, record ranges and stop". Nobody can tell whether that stop fires until a writing run exists, so the cheap half is a census: for the M5.34 result tile and the manifests it rebuilds, does the new byte length fit the FAT cluster chain `imgpatch` would reuse, and if not, by how much and which file. No write, no image copy. This is the rule-17 first slice of M5.30.
  - Precheck: `python3 tools/imgpatch.py --selftest` passes; the M5.34 report names the changed tile and the rebuilt manifests (`~/projekty/leafre-work/m5.34/report.json`); `python3 tools/selftest.py --only cardcheck` passes (and `python3 tools/cardcheck.py --root ~/projekty/leafre-work/m5.29-factory-root --fast` prints `RESULT: PASS`; the old `cardcheck.py --selftest` is not a flag and exits 2).
  - Scope: one subcommand (name in the PR) on `tools/imgpatch.py` or a new `tools/fit_census.py` that, given a card image and a generated tree, prints per file: factory on-disk bytes, generated bytes, delta, cluster chain slack, `fits` / `needs_relocation`. Reads the image; writes nothing. Reuses the M5.34 output tree as the input, plus one synthetic over-budget case.
  - Input: EXP-2026-11-17-M5.34-parcel (`tile_diff`, `tree_diff`), EXP-2026-11-18-M5.45-idempotence (append/in-place semantics), M5.29's rebuilt manifests, `tools/imgpatch.py` (chain walk), `tools/cardcheck.py`.
  - Hints: the tile grew +138,994 B at level 2 and +4,671,350 B at level 1; the first question is the level-1 figure against the factory chain slack, because that is the run M5.34 actually made. A file with slack >= delta is a one-variable card; report the smallest slack in the tree so M5.30 knows if it is a one-file or an all-files problem.
  - Done when: the census prints per-file `fits`/`needs_relocation` with the slack and delta, for the real M5.34 tree and for one synthetic over-budget file (control); a `--selftest` on synthetic FAT data covers fit, exact fit and over-budget; `python3 tools/selftest.py` green.
  - Stop: if the answer needs a real image copy to be trusted (FAT quirks), deliver the census on the real image and hand the write to M5.30 rather than copying images here.
  - Falsifier: the census reports `fits` for a file whose delta exceeds its chain slack, or a synthetic over-budget file with spare slack is reported `needs_relocation`.
  - Work (driver, 2026-11-19): `tools/fit_census.py` + `EXP-2026-11-19-M5.47-fit-census.md` (C-4560–C-4569); level-1 tile `needs_relocation` (slack 22,272 B vs delta +4,671,350 B, 71 extra clusters), level-2 too (+138,994 B, 2 clusters), factory tree 480/480 `fits`, and `imgpatch --allow-resize --dry-run` refuses with `internal-range` (allocator takes clusters 115,187+ past the partition's last valid 115,186).
  - Result: `docs/experiments/EXP-2026-11-19-M5.47-fit-census.md` (C-4560–C-4569). Census on the real EU 2011 image: factory tree 480/480 `fits` (delta 0); level-1 tile `MAPAL001/B48R058R.DAT` +4,671,350 B vs 22,272 B slack -> `needs_relocation`, +71 clusters; level-2 +138,994 B -> +2 clusters; smallest slack in the tree `REFER001/ADDRE029.DAT.cmp` 217 B, so it is a one-file problem. `--selftest` OK (43 checks), `selftest.py` 94 passed / 0 failed / 23 skipped, `gate.py` 4 pass / 0 fail / 0 skip, `claims_check --strict --count-check` OK.
  - Round 2 (navigator review): Precheck replaced with `selftest.py --only cardcheck` + `cardcheck --root … --fast` (the old `cardcheck.py --selftest` exits 2); C-4562 corrected (DRSTR001 length-same/bytes-differ, C-4569); "changed" defined as non-zero delta (two files differ by bytes); §6 geometry relabelled `data_area_end`/`partition_end`; C-4567 ratios dropped; C-4568 (allocator identity) and C-4569 added; `--delta-probe` added (real-image `delta == slack` / `slack + 1` control, selftest 43).
  - Claims: C-4560–C-4569

- [x] **M5.48 — `tilewriter` leaves a partial `--out` tree when the build fails, so a failed run looks like a card**
  - Status: done · Owner: task/m5.48-partial-out · Critical: no · Pair: solo
  - Depends: — (the behaviour is on `main`; `one_tile_pipeline` copies the factory root before the tile build)
  - Goal: M5.44's and M5.45's refused runs both leave a full copy of the factory root at `--out` with no tile change (M5.44's EXP records it as a candidate task). A later script that tests `os.path.isdir(out)` reads a failed run as a built card; the M5.35 bundle and the M7.1 mass run both do that kind of test. The fix is one cleanup path plus one check that a later task can rely on.
  - Precheck: `python3 tools/one_tile_pipeline.py --selftest` passes; in a scratch dir, `--parcel` a preserve-only directory and `ls --out | wc -l` prints 480 with the run's exit non-zero.
  - Scope: `tools/one_tile_pipeline.py` only: build into a sibling temp dir and rename on success, or remove the partial `--out` on any non-zero exit, whichever keeps the error message and the `--json` report intact; a `--selftest` case that a refused run leaves no `--out` (or leaves it only with `--keep-partial`).
  - Input: EXP-2026-11-18-M5.44-level2 (the negative control that left the tree), EXP-2026-11-18-M5.45-idempotence (same behaviour), `tools/one_tile_pipeline.py` (`build_factory_out`, the copy step).
  - Hints: do not delete a directory the user passed if it already existed before the run — only a tree this run created. The M5.34 evidence dir under `~/projekty/leafre-work/m5.44` is kept on purpose, so do not touch it.
  - Done when: the refused-run selftest asserts no `--out` is left; `python3 tools/one_tile_pipeline.py --selftest` green; `python3 tools/selftest.py` green.
  - Stop: if the copy is needed by a later stage that runs on failure (a diff of the partial tree), make it `--keep-partial` opt-in and say so in the EXP; do not remove the ability to inspect a failed run.
  - Falsifier: a refused run still leaves a 480-file `--out` with no `--keep-partial`.
  - Claims: C-4570–C-4579
  - Result: EXP-2026-11-19-M5.48-partial-out.md; `tools/one_tile_pipeline.py` removes a `--out` tree it created on a non-zero exit (refused run: `state=removed`, `files_left=0`, `tilewriter_rc=1`), `--keep-partial` keeps the 480-file failed tree, a non-empty pre-existing `--out` is refused exit 2 with `KEEP.ME` byte-identical and no report (`--force-overwrite` replaces it, an empty `--out` stays empty), and a success splice (`--parcel 76,940 --level 2`) keeps its 480-file tree at exit 0; new `--selftest` cases (red on a removal-disabled mutant). Checks: `selftest.py` passed=93 failed=0 skipped=23 total=116, `gate.py` 4 pass / 0 fail / 0 skip, `claims_check --strict --count-check` OK; C-4570–C-4579.

- [x] **M5.49 — P1 is one contained tile and nothing copies it: a display-only card whose only diff is that factory tile**
  - Status: done · Owner: task/m5.49-p1-verbatim-tile · Critical: yes · Pair: required
  - Note (M9.13, 2026-11-20): software evidence for the factory-backed splice: the firmware's mount reads a `tilewriter.py --factory` `B48R058R` (two ways in a `0x2046` directory) read-for-read like the factory tile (C-3253). A fresh-container tile is not readable: every directory must be backed by the fixed length the firmware reads (`0x8100` for section 1 level 1; C-3256, C-3257). Check a card's tile with `python3 tools/datask_l3.py mount … --position LAT,LON --replace MAPAL001/<tile>=<file> --json B.json` then `diff`. Corrected by M5.56 (DRSTR001 clamp; tilewriter pads), C-5832/C-5833.
  - Depends: M5.46 (done — `contained=1`, B48R058R is the whole test box), M5.30 (done — the relocation tooling and the one-variable card)
  - Goal: M5.46 answered *how many* tiles P1 needs (one) and M5.30 proved the writer can turn a changed tile into a card that passes `cardcheck`/`7z`/`fsck` with an enumerated diff. What is not done is the P1 rung itself: a card whose Dolnośląskie region is the **factory** B48R058R copied verbatim, with the display-only gate recorded. Without it P1 is a census and a promise, and P0 → P1 has no measured step.
  - Precheck: `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json <factory ROOT>/MAPAL001 | tail -1` prints `census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45`; `python3 tools/cardcheck.py --root ~/projekty/leafre-work/m5.29-factory-root --fast` prints `RESULT: PASS`; `python3 tools/imgpatch.py --allow-resize --dry-run` on the factory tile is a delta-0 no-op — say which.
  - Scope: `tools/one_tile_pipeline.py` (a `--preserve-tile MESHTAG` mode: write the factory tile bytes verbatim into `--out`, rebuild only `DRSTR001.DAT` if its length must change, write M5.41's expected-change-set) plus a P1 profile check; **no** OSM ingest, **no** tilewriter change, **no** new format claim. The display-only gate is a row in the EXP: which M5.34/M5.30 checks it must pass and which routing checks it deliberately fails (M5.16 open).
  - Input: EXP-2026-11-18-M5.46-containment, EXP-2026-11-19-M5.30-one-variable-card, EXP-2026-11-19-M5.47-fit-census, `profiles/dolnoslaskie-test.json`, `tools/one_tile_pipeline.py`, `tools/mkcard.py`, M5.41's expected-change-set (block if it is not on main; do not duplicate it).
  - Hints: a verbatim factory tile has delta 0, so M5.47's fit question does not fire — say that in the EXP (that is why P1 is cheaper than P0's change). The card is only meaningful if `cardcheck --image` and a diff against the factory *image* both pass; a tree-only check is the M5.44 defect class. Do not claim the car displays it — that is L5.
  - Done when: `python3 tools/one_tile_pipeline.py --preserve-tile B48R058R --out <S>/p1` builds a 480-file tree; `cardcheck.py --root <S>/p1` PASS; patching the factory image with that tree (M5.30's Reproduction) leaves a card whose `--check-diff` is confined to `DRSTR001.DAT`+dir entries (delta 0 tile ⇒ the tile does not move) and passes `cardcheck --image`; the EXP names the display-only vs routing gate split; `python3 tools/selftest.py` and `tools/gate.py` green.
  - Stop: if a verbatim factory tile cannot be the only region of a card without a new DRSTR format change, record the exact byte that resists and hand it to a format task; do not widen the diff to make P1 pass.
  - Falsifier: the P1 tree reports 480 files but `cardcheck --image` on the patched copy fails, or the diff touches any cluster outside `DRSTR001.DAT`/its dir entry (the tile's clusters must be identical to factory).
  - Claims: C-5380–C-5389 (moved 2026-11-20: C-4590–C-4599 belong to M4.41's EXP)
  - Result: EXP-2026-11-20-M5.49-p1-verbatim-tile.md. `--preserve-tile B48R058R` builds a 480-file P1 tree (tile 289,319,168 B / `e9c9cb22…8af3ff52` copied verbatim, `tile_delta=0`, whole-tree diff against the factory root empty) and `cardcheck --root` PASS; patching the factory image copy is a delta-0 no-op (`check-diff` `0 range(s)`, `cardcheck --image` PASS, `cmp` says the card is byte-identical to factory `105e2032…76307`, so M5.30's relocation does not apply); the display-only split (routing/class/names NOT-APPLICABLE, firmware CANNOT-VERIFY-OFFLINE) is in the report and EXP §4; the report runs `l2check` rather than assuming it, so `l2check_ok=false` (`counts.l2check_rc=1`, tile checked) honestly records the pre-existing M5.52 `refer_rename_resize` regression (C-5543/M5.55, fails on the untouched factory root too), and a synthetic fixture reports it not-run (§5); the P1 profile check runs before the file probe, so a **present** not-contained factory tile is refused by containment (`--preserve-tile B48R050R` on `profiles/dolnoslaskie-test.json`: rc 1, `real_image_run=refused-not-contained`, `class=outside`, no `--out`; `--no-profile-guard` accepts it), and the contained tile records `containment.class="contained"` (§6); `card-ladder.md` P1 rows 3–5 are now runnable. Negatives: a missing cell is BLOCKED with no `--out`, a flipped tile byte is `1 range(s)`. Checks: `selftest.py` 137/0/23 (160), `gate.py` 4 pass / 0 fail / 0 skip, `claims_check --strict --count-check` OK; C-5380–C-5389.

- [x] **M5.50 — the card ladder page P1 needs: one row per rung, each a command with an expected string**
  - Status: done · Owner: task/m5.50-card-ladder-page · Critical: no · Pair: required
  - Depends: M5.46 (done), M5.30 (done), M5.44/M5.45 (done)
  - Goal: no page says what "P1" *is as a check* — the ladder lives in TODO prose and the Priorities commands, so every pass re-derives it and the rule-17 card row is a hand command. M5.38 (open) defines P1 as "all Dolnośląskie display-only", but no page says which gates that means or what P2 (routing) adds. One page, one row per rung, each row a runnable command with its expected output, stops the "P1 = one tile or many?" drift.
  - Precheck: `grep -rn 'P0\|P1\|P2' docs/format/*.md profiles/*.json | head` shows no single page owns the ladder; `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json <ROOT>/MAPAL001 | tail -1` prints the census the page must cite.
  - Scope: one docs page (`docs/format/card-ladder.md`) plus a pointer from `docs/format/map-tiles.md` and `TODO.md`'s L2 bullet; each rung row names (a) the profile/region, (b) the tile set, (c) the gate commands with exact expected strings, (d) what the rung deliberately does *not* prove. **No** code change except a thin consumer of `map_signals` (H109 owns it; link, do not duplicate).
  - Input: H109 (map_signals), M5.46 census, M5.30 card, M5.34 parcel, `profiles/`, `docs/format/ze0-tools.md`, the Priorities rule-17 block.
  - Hints: the page's value is that its commands fail loudly — a rung row with "reference says X, got Y" and a non-zero exit, not prose. Cite H109's tool by path; if H109 is not on main yet, write the commands and have H109 replace them with the call.
  - Done when: `docs/format/card-ladder.md` exists with one row per rung P0/P1 (and a P2 placeholder naming M5.16/M5.36 as the routing gates it adds); every command in every row runs and prints its expected token on this host (paste outputs); `grep -c 'card-ladder' TODO.md` finds the L2 pointer; `python3 tools/gate.py` 4 pass; no claim is registered (a page of existing facts).
  - Stop: if a rung has no runnable gate yet (P2 routing is M5.16, open), leave it as an explicit `NOT RUN — M5.16` row rather than inventing a check.
  - Falsifier: a rung row's command exits 0 but does not print the token the row says it must, or the page restates a number without the command that prints it.
  - Result: EXP-2026-11-19-M5.50-card-ladder.md. `docs/format/card-ladder.md` has P0 (10 rows), P1 (5) and P2 (6) as commands with expected tokens; its 40-line block prints 16 x `OK:` + `card-ladder: all rows OK`. P0's card row is the M5.30 SHA `b0faf119...33237`; P1's three card rows are `NOT RUN - M5.49` and the absent `--preserve-tile` flag is itself asserted (`0`); P2's routing/class rows name M5.16/M5.36. Two negative controls (wrong token, a NOT RUN row asserted as present) fail the block. No claim registered; no code touched. Self-reviewed (router down), recorded in the EXP.
  - Claims: none yet (docs page; the commands cite existing claims)

- [x] **M5.55 — l2check `refer_rename_resize` expects the pre-M5.52 edit and FAILs on every EU card**
  - Status: done · Owner: task/m5.55-l2check-resize · Critical: yes · Pair: required
  - Step: P1
  - Depends: M5.52 (done)
  - Goal: since M5.52 (`608f949`) `mutate_refer_poi.py --resize` also patches the field-5 length byte, but `l2check.check_refer_rename_resize` still builds the expected record as "rename only" (`tools/l2check.py` ~line 881). Every full `l2check` run on an EU tree now ends `RESULT: FAIL` with `record 8 is not the rename-only edit (got 84 bytes, expected 84)`, including the untouched factory tree, so the `l2check` gate of `one_tile_pipeline` (and of every P1 run) cannot PASS (found by M5.54, EXP-2026-11-20-M5.54-wide-kinds).
  - Precheck: `python3 tools/l2check.py --root FAC --no-golden --tiles B48R058R.DAT --semantic-tiles B48R058R.DAT --cmp-limit 20 | tail -3` prints the `refer_rename_resize] FAIL` line and `RESULT: FAIL` on the EU factory tree.
  - Scope: `check_refer_rename_resize` in `tools/l2check.py` (the expected bytes include M5.52's field-5 length patch) and an l2check self-test case for it; no change to `mutate_refer_poi.py`.
  - Input: EXP-2026-11-19-M5.52-resize-field-len, `tools/mutate_refer_poi.py --resize`, `tools/l2check.py`.
  - Done when: the Precheck command prints `[refer_rename_resize] OK` and `RESULT: PASS` on the EU factory tree, and a negative (a resize edit that leaves field 5 stale) FAILs.
  - Stop: if field 5 is not the only extra byte that `--resize` changes, block and name the byte.
  - Claims: C-5550–C-5559
  - Result: EXP-2026-11-20-M5.55-l2check-resize-expectation. `check_refer_rename_resize` builds the expected record through the new `_expected_resize_record` (rec[1] `len2` **and** the field-5 length byte, field 5 from `mutate_refer_poi.name_field`), so on the EU factory tree `[refer_rename_resize] OK (… records=39; changed_records=1)` and `RESULT: PASS`; the pre-fix run printed `record 8 is not the rename-only edit (got 84 bytes, expected 84)` / `RESULT: FAIL`. The only stale byte was `rec+0x21` (field-5 7→9 words); reverting it alone still FAILs at the same 84-byte length, and the l2check selftest carries that negative. `mutate_refer_poi.py`/`validate_mutation.py` unchanged; `docs/format/` unchanged. C-5550–C-5552; closes C-5543's l2check gate.

- [x] **M5.56 — A tile written without a factory container must survive the firmware's directory reads**
  - Status: done · Owner: task/m5.56-no-factory-container · Critical: no · Pair: required
  - Step: P1
  - Depends: M9.13 (done); M3.31 helps (the rule instead of the observed constants)
  - Goal: the fresh-container writers (`tilewriter.py` without `--factory`, `one_tile_pipeline.py --synthetic`) produce a tile the firmware cannot mount: its first directory read (`0x8100` bytes at `0x1100`) runs past the end of the 22,272-byte file and fails with status `-1` (EXP-2026-11-20-M9.13, C-3256). Every tile outside the factory coverage will be written this way, so the writer has to back each directory with the length the firmware asks for.
  - Precheck: `python3 tools/one_tile_pipeline.py --synthetic --cell B48R058R --out syn`, then `python3 tools/datask_l3.py mount archive/head256.img --card-image <EU card> --position 51.70,17.45 --replace MAPAL001/B48R058R.DAT=syn/MAPAL001/B48R058R.DAT --json S.json` shows one read handled by `0x0041597c` with status `-1`.
  - Scope: the fresh-container path of `tools/tilewriter.py` only (padding or layout of directories; the section list at header `0x800` must still describe the file). No change to the `--factory` path. `clarion_tile.read_tile` must still decode the tile.
  - Input: EXP-2026-11-20-M9.13-generated-tile-l3 (run S), `docs/format/map-tiles.md` ("What the mount reads of a tile, and a generated tile"), `tools/datask_l3.py diff`.
  - Done when: in the Precheck run on the new tile no read of `B48R058R.DAT` has a negative status and the mount reads at least one directory per section the tile declares; `python3 tools/tilewriter.py --selftest` and `python3 tools/l2check.py` on the tile PASS; the unchanged `--factory` tile still compares SAME to the factory run (`datask_l3.py diff F.json G.json`).
  - Stop: if the firmware then rejects the tile for a reason other than a short read, record the read and the handler and block with a follow-up.
  - Falsifier: the padded tile mounts, but so does a control with one directory truncated below the read length (then the comparison is not testing the lengths).
  - Claims: C-5830–C-5839
  - Result: EXP-2026-11-20-M5.56-no-factory-container. The firmware asks `min(0x100 * T[kind].n, size - pos)` with `size` from `DRSTR001.DAT`: the factory's last section-4 directories are read short (`0x2900`, `0x5d00`) and parsed. The run-S failure (C-3256) came from `--replace` keeping the factory DRSTR001 size; with the true size the unpadded tile mounts, with `0x100` too much it fails. `tilewriter.py` (fresh path only) now zero-pads to the longest directory read (`pad_directory_reads`, 22,272 → 37,376 B): Precheck run has no negative status, the one declared directory (section 1; sections 2/4 declare none) is read and parsed by `0x00414dbc` (16,514 B); cut `0x100` short → -1 (falsifier control); targeted `l2check` PASS, `tilewriter --selftest` 89/89; `--factory` F/G SAME (28 reads). New `dir_read_len.py drstr-size`. C-5830–C-5834.

- [x] **M5.59 — `lev3456gen.py`: put level-3 roads in the directory whose box holds them**
  - Status: done · Owner: task/m5.59-lev3-dir-box · Critical: no · Pair: solo
  - Step: P2
  - Depends: M5.16 (generator exists), M9.18 (directory-level L3 check, blocked only on records)
  - Goal: `lev3456gen.py` maps a point to a level-3 directory with a proportional 9 × 5 grid over the database bounds (`l3_cell_for_point`), not by the directory boxes. A Krotoszyn extract (51.70 N 17.45 E) lands in dir 22 (box x −104…−96, the London cell); the firmware at Krotoszyn reads dir 24 (C-2445, EXP-2026-11-20-M9.18). Every generated level-3 road is in the wrong place on the coarse map.
  - Precheck: `python3 tools/lev3456gen.py generate --template <EU LEV3456R> --extract tools/fixtures/m9.18-krotoszyn-lev3456.json -o G.DAT` then `python3 tools/mount_dirs_l3.py changed <EU LEV3456R> G.DAT` lists `s1 L3 dir 22`.
  - Scope: `tools/lev3456gen.py` level-3 split/quantisation only: choose the directory from `Dir.box` / head (`y = 1.5·lat`, stored `x = lon − 100`, map-tiles.md "Directory geometry"), the 16 × 16 parcel inside it, and quantise against that parcel. Check levels 4/5 against the same geometry (parcel `w0`/`w1` codes, map-tiles.md C-2805) and fix only if wrong. No container change.
  - Input: EXP-2026-11-20-M9.18-lev3456r-sec4-l3, `tools/mount_dirs_l3.py changed`, `tools/lev3456.py` (`Dir.box`, `decode_record` header code), `docs/format/map-tiles.md` (directory geometry, parcel code row).
  - Done when: the Precheck run lists `s1 L3 dir 24` (and no other level-3 directory) for the fixture; `datask_l3.py mount --position 51.70,17.45 --replace MAPAL001/LEV3456R.DAT=G.DAT` + `mount_dirs_l3.py check` gives 9/9 MATCH and the directory it reads at Krotoszyn is one `changed` lists; `lev3456gen.py --selftest` and `lev3456.py verify G.DAT` pass; a second position (London: dir 22) as control.
  - Stop: if the level-3 parcel code in the record header (`w0`/`w1`) contradicts the box geometry, record both and stop.
  - Falsifier: the fixed generator still changes a directory whose box does not hold the extract.
  - Claims: C-6100–C-6109
  - Result: EXP-2026-11-20-M5.59-lev3-dir-box. The level-3 directory is now chosen by its box (`y = 1.5·lat`, stored `x = lon − 100`, 0.5-unit parcels): the Krotoszyn fixture changes `s1 L3 dir 24` only, the firmware mount there reads that directory (`MATCH 9/9`, `SAME-RELOCATED`), London control → dir 22. New `lev3456gen.py placement` decodes every changed record back to lat/lon and requires it on a road (worst 1.08 steps; the old generator FAILs), new `codes` shows the record header is the geometric parcel code on 13,142/13,142 factory records of levels 3/4/5 (0 with a shifted column), so the generator computes it instead of copying. Levels 4/5 were already right. C-6100–C-6109.

- [x] **M6.13 — Prepare the S3 bench package manifest (no hardware, no vendor bytes in repo)**
  - Status: done · Owner: task/m6.13-s3-bench-manifest · Critical: yes
  - Depends: M5.14 (S3 done), M5.24 (diff proof), M9.31 (runnable L3 evidence)
  - Pair: solo
  - Goal: make the S3 (LEV3456) bench run cheap when hardware returns: record artifact SHA-256/size/diff ranges, how it differs from S0/S1/S2 (one variable), which offline/L3 gates passed, and S3 pass/fail criteria. Image stays outside repo.
  - Precheck: `docs/research/card-test-plan.md` defines S3 criteria; M5.14/M5.24 EXPs name image/diff-ranges or package records `UNRECORDED`; `todo_check.py`/`claims_check.py` pass.
  - Scope: `docs/research/bench-packages/s3.md` (or a defined section in `bench-evidence-pack.md`) with manifest fields and reproducible hash/size verification commands outside repo. No flashing, no L5 claims.
  - Input: M5.14 EXP, M5.24 diff proof, M6.3/M6.7 plan, M9.31 runnable L3 evidence (or `l3check`/`progress_report` output).
  - Done when: manifest lists artifact path placeholder + SHA-256 + size + diff ranges + base image identity, states "L5 NOT RUN", links pass/fail criteria; negative control: S2 manifest/criteria kept distinct (one variable).
  - Stop: if hash/diff ranges are not recoverable from recorded EXPs, record `UNRECORDED` and file follow-up; do not guess.
  - Claims: C-3230–C-3239
  - Result: EXP `docs/experiments/EXP-2026-11-19-M6.13-s3-bench-manifest.md`; package `docs/research/bench-packages/s3.md` (L5 NOT RUN): artifact `us_S3.img` placeholder, SHA-256 `186f2ded…9775c1`, 8,057,257,984 B, base `53342430…c5383` (re-hashed), allowed ranges dir `[106124352,106124384)` + clusters 8–38 `[106189824,108221440)` re-resolved on the real base (C-3230), expected diff 117 B in `[107324608,107324896)`; L1/L2 PASS, L3 NOT-YET-AVAILABLE; S3 = factory + one tile, S2 pair ranges disjoint and S2 rename absent (negative control, C-3231). Two gaps filed as **M6.16**: no S3 generator in repo, and the moved vertex is ~45 m at 20.0–20.667°N by the M5.44 grid vs C-2054's ~11.6 km at 20.82°N.

- [x] **M6.17 — Say what on the map card is code and what LeafSDTools "SRAM" is**
  - Status: done · Owner: claude/project-thread-64ftoc · Critical: no
  - Depends: —
  - Goal: answer Marek's question "only maps on the card, or the software too; does the system boot from it" from the ledger and the LeafSDTools source.
  - Done when: EXP-2026-11-19-M6.17-card-what-runs gives the card layout with code/data per region and the meaning of the SRAM/VFlash dump, each with a status.
  - Result: card = MBR + CE ROMs A/B/C (OS + Navi.exe, ~38 MB) + FAT32 maps + TFAT16; update mode runs B from the card (VERIFIED, LeafSDTools); normal mode from the card is a strong HYPOTHESIS (unit flash is 8 MiB); "SRAM" dump = 1 MiB user data from flash (C-5190–C-5194).
  - Claims: C-5190–C-5199

- [x] **M6.16 — S3 card: a committed generator and the true on-screen place of the moved vertex**
  - Status: done · Owner: task/m6.16-s3-generator · Critical: no
  - Pair: solo
  - Depends: M6.13 (done — the package that names both gaps), M5.14 (the edit), M5.44 (the level-1/2 grid)
  - Goal: the S3 bench card (`docs/research/bench-packages/s3.md`, `186f2ded…9775c1`) has no generator in the repo (M5.14 ran `/tmp/m5_14_patch.py`), and its expected place on screen is doubtful: C-2054 says 20.82→20.92°N (~11.6 km) while the M5.44 grid puts directory (30,65280) at 20.0–20.667°N with +40/2048 units ≈ 45 m. A lost image or a wrong place to look wastes a bench session.
  - Precheck: `python3 -c "import sys;sys.path[:0]=['tools/ze0-viewer/tools_ze0','tools'];import parcel_census as p;print(p.directory_bbox(1,30,65280))"` prints `lat_min 20.0 … lat_max 20.667` and `lon_min 64356.0` (the lon is wrong for the US mesh); `ls tools | grep -c m5_14` prints `0`.
  - Scope: one tool (name in the PR, e.g. `tools/s3_vertex_patch.py` with `--selftest`) that applies M5.14's in-place edit (dir (30,65280) slot 8 rec k=17, layer 8 shape 1 vertex 2, +40,0; zlib 9, NUL-pad to 288 B at `0x1150c0`) and reproduces tile `fc4d4bfc…` and, through `imgpatch.py`, image `186f2ded…`; a US-capable `mesh_to_lon` (or a stated mapping) and the vertex's lat/lon before/after, updating C-2054 via a new row if it changes; the S3 package's "Expected place" row. If the bench protocol stacks stages, also the S2-based variant with its SHA-256.
  - Input: EXP-2026-11-08-M5.14 (Method, the patch description), EXP-2026-11-19-M6.13-s3-bench-manifest, `tools/ze0-viewer/tools_ze0/clarion_bg.py` (`parcel_geo`, `mesh_to_lon`), `tools/coord.py`, the US image (`fetch_image.py --image US`).
  - Done when: the tool reproduces `fc4d4bfc8365647c…` byte for byte from the factory tile and the image SHA-256 `186f2ded…` (or names the byte that differs); the vertex lat/lon is computed by the M5.44 grid with a positive control (a factory feature at a known place on the US card) and recorded in s3.md; `selftest.py --only <tool>` green.
  - Stop: if the tile does not reproduce after the described edit, record the differing bytes and set the S3 package's artifact to "regenerate before bench" instead of trying a fourth reconstruction.
  - Claims: C-5250–C-5259
  - Result: EXP `docs/experiments/EXP-2026-11-20-M6.16-s3-generator.md`; `tools/s3_vertex_patch.py` (selftest 18 checks) reproduces the patched tile `fc4d4bfc…` and the S3 image `186f2ded…` byte for byte from the factory US image (117 B in `[107324608,107324896)`, cardcheck PASS, C-5250). The directory `x` word is signed `mesh_x − 1024` (65280 → lon −156); the level-1 grid hits Ka Lae/Upolu/Kumukahi within 161/202/1,068 m, y-flip and C-2054's reading miss (C-5251). The vertex moves **63.8 m east** at 20.1672°N 155.7218°W, north Kohala, island of Hawaii (C-5252; C-2054 retracted); s3.md "Expected place", "Generator" and "Stacked variant" rows updated. S2 is not reproducible today (`1f1b444e…` ≠ `af4c9ff1…`; S3-on-today's-S2 `fc1433d2…`, C-5253) → **M6.20**.

- [x] **M6.20 — S2 card: a generator that reproduces `af4c9ff1…`, or a re-pinned S2**
  - Status: done · Owner: task/m6.20-s2-generator · Critical: no
  - Pair: solo
  - Depends: M6.16 (done — found the gap), M5.13b (the S2 recipe)
  - Goal: the card plan stacks stages (S3 starts from the accepted S2), but the recorded S2 image `af4c9ff14e6b2749…` (M5.13b, C-2351) has no generator: today's `mutate_refer_poi.py --page 0x840ba0 --old "HANA HEALTH CENTER" --new "OSM2LEAF TEST POI1"` (default and `--whole-blob`) writes a 4,240,425 B `.cmp` (`b4ef43b9…`) where M5.13b wrote 4,233,336 B, giving S2 `1f1b444e…` (C-5253). A bench session that loses `us_S2.img` cannot rebuild it, and the stacked S3 hash depends on it.
  - Precheck: `python3 tools/mutate_refer_poi.py <factory POINT010.DAT.cmp> <.ind> OUT --page 0x840ba0 --old "HANA HEALTH CENTER" --new "OSM2LEAF TEST POI1"` prints `outer .cmp 4240574 -> 4240425` (not 4233336).
  - Scope: find which M5.13b-era code path (git history of `tools/mutate_refer_poi.py` / `cmpind_writer.py` before the chunk-preserving default, M9.43) wrote 4,233,336 B, and either pin it as a flag that reproduces `af4c9ff1…` through `imgpatch.py`, or record a new S2 SHA-256 from today's tool in the S2 record (and the S3 package's "Stacked variant" row) with the reason.
  - Input: EXP-2026-11-08-M5.13b-us-s1-s2, EXP-2026-11-20-M6.16-s3-generator (C-5253), the US image (`fetch_image.py --image US`).
  - Done when: one committed command produces an S2 image whose SHA-256 equals `af4c9ff1…` (or the EXP names the first differing byte and the S2 + stacked-S3 hashes are re-pinned in the records), with `imgpatch --check-diff` 0 outside.
  - Stop: if no historical code path gives 4,233,336 B after two candidates, re-pin instead of reconstructing further.
  - Claims: C-6200–C-6209
  - Result: EXP `docs/experiments/EXP-2026-11-21-M6.20-s2-generator.md`; the recorded S2 `af4c9ff1…` is reproducible: `mutate_refer_poi.py --page 0x840ba0 --old "HANA HEALTH CENTER" --new "OSM2LEAF TEST POI1" --legacy-m513b --whole-blob` (zlib-ng 1.3.1, the pre-M5.25 pad + L9 fallback) writes `.cmp` `c2b9c388…` (4,233,336 B), and two `imgpatch` writes give `af4c9ff1…c578e911` (cardcheck PASS, C-6200/C-6201). That image is **corrupt**: the pad zeroes 204 B of an abutting page at `0x84b234` (C-6202), so the S2 record and the S3 stacked row are re-pinned to the valid S2 `1f1b444e…` (C-6203) and stacked `fc1433d2…` (C-6204); `--check-diff` cannot see it (C-6205).

- [x] **M8.A3 — Built-in loader** (`kernel=0x3e00200`, `app=0x200200`):
  parse `ECEC`/`ROMHDR`, copy B/C and A to `physfirst & 0x1fffffff`, PC =
  `nk.exe` entry. Done when booting needs no `-device loader`.
  - Status: done · Owner: task/m8.a3-builtin-loader · Critical: no
  - Depends: M8.A2
  - Done when (made concrete 2026-11-20, the original line is kept above):
    `-M ze0 -kernel archive/head256.img` with no `-device` option puts RAM
    bytes identical to the physfirst..physlast cuts of images B and A,
    starts at PC `0x8800ebd0`, and its 60 s non-interrupt exception
    sequence equals the `-device loader` boot's; a wrong offset exits
    non-zero.
  - Result: EXP-2026-11-20-M8.A3-builtin-loader (C-1250–C-1253). Patch
    `tools/qemu-ze0/patches/ze0-0004-hw-sh4-ze0-builtin-loader.patch`;
    options are `kernel-off=`/`app-off=` (`kernel` is QEMU's `-kernel`
    property). RAM byte-identical, PC `0x8800ebd0`, 30-event fault
    sequence identical in 2 + 2 boots; old short cuts differ (0 events).
    `run.sh` uses `-kernel` on ze0 and ROMHDR lengths on `-M none`
    (C-1283 fixed). Tool: `tools/ze0_ceload.py`.
  - Claims: C-1250–C-1259

- [x] **M8.A9 — Port the `ze0` patch series to current QEMU (11.1.3)**
  The five patches in `tools/qemu-ze0/patches/` are pinned to 8.2.7. Port the
  **intent** of each patch, not its diff: the per-hunk intent tables are in
  `tools/qemu-ze0/patches/README.md` §§1–6 and the measured delta is
  [`docs/research/qemu-ze0-port-delta.md`](docs/research/qemu-ze0-port-delta.md).
  - Status: done · Owner: task/m8.a9-qemu-11-port · Critical: no
  - Depends: — (M8.A2 is merged; this is a port, not a re-run)
  - Goal: `-M ze0` works on current QEMU, not only on the frozen 8.2.7 pin.
  - Precheck: reproduce the two application columns in the delta doc for
    yourself; they disagree on purpose. With `build.sh`'s own invocation
    (`patch -p1 --forward --batch`) on pristine 11.1.3, `0002`, `m8a4-0001`
    and `m8a4-0002` apply `rc=0` but `m8a4-0003` fails 4 of 7 hunks and
    `ze0-0001` fails 4 hunks; with strict `git apply --check`, 4 of 5 reject.
    The gap is fuzz, which is why this task is judged by a **build**, not by
    apply success. Then, for each failing hunk, name the 11.1.3 symbol that
    replaced what it used. Do not edit until every hunk has a named
    replacement or `NEEDS HUMAN`.
  - Scope: (1) **Trap first:** the UTLB/ITLB helpers are *not* removed;
    they are spelled `mmaped` (one `p`), all eight at
    `target/sh4/helper.c:514-711`, declared `target/sh4/cpu.h:259-273`, so
    the CCN body is a mechanical copy, not a rewrite. (2) `sh4-ccn`:
    includes `exec/memory.h`→`system/memory.h`, `hw/qdev-core.h`→
    `hw/core/qdev.h`, `exec/exec-all.h`→`exec/cputlb.h` (`tlb_flush`);
    `DeviceClass.reset` → `device_class_set_legacy_reset()` (field is
    `legacy_reset`); keep MMUCR/PTEH side effects and the array window.
    (3) `ze0_stubs`: same include renames, same reset setter.
    (4) `sh7750.c` de-duplication: hand-apply hunks 1, 3, 6 — the `devices[]`
    context line is gone, and 11.1.3 deliberately dropped the `abort()` on
    an ITLB-data write that the copied block keeps; decide which semantics
    to port and say so. (5) Machine: `config ZE0` with `default y` +
    `depends on SH4` in Kconfig (11.1.3 no longer lists boards as
    `CONFIG_*=y` in `default.mak`), `"cpu.h"`→`"target/sh4/cpu.h"`,
    `hw/{boards,loader,qdev-properties}.h`→`hw/core/…`,
    `sysemu/sysemu.h`→`system/system.h`; `SHIX` is gone from 11.1.3, so both
    meson hunks must be inserted by hand. (6) Pin policy: a **tested range**
    (8.2.7 ✔ measured, 8.2.10 ✔ measured, 11.1.3 target) instead of one
    frozen version, plus `build.sh --check-version X` that applies the series
    and prints a verdict without building.
  - Done when: on pristine 11.1.3 the ported series builds `qemu-system-sh4`,
    `-M help` lists `ze0`, and `-M ze0` boots `archive/head256.img` ≥10 s
    with 0 CPU exceptions and the same stable access list as the 8.2.7 pin
    (one `write 0x38`, C-4311); `ce_qemu_probe.py --qemu <11.1.3 build>` is
    recorded as the oracle comparison **with its version stated**, since the
    15-entry list reproduces only against 8.2.7; `build.sh --check-version`
    exists and its selftest covers both tuples.
  - Stop: if a ported hunk has no equivalent in 11.1.3 (the ITLB-data
    `abort()` is the known one), stop at that hunk, record the decision as
    `NEEDS HUMAN`, and do not invent a new MMU path.
  - Claims: C-4320–C-4329
  - Result: done — `tools/qemu-ze0/patches/11.1/` is the series for QEMU
    11.1.3 (12 patches; the task text counted five, the series had grown).
    It applies without fuzz, `build.sh --version 11.1.3` builds it and
    `-M help` lists `ze0`. A 10 s boot of `archive/head256.img` gives the
    same kernel debug text (13,949 bytes), the same 2,920 API traps, the same
    7 interrupts and the same 138 unmodelled accesses as the 8.2.10 build
    (`tools/qemu_boot_cmp.py`, C-4321); `ce_qemu_probe.py` prints the same
    15-entry list on both. The literal oracle "0 exceptions, one `write
    0x38`" is obsolete on both versions (C-4326) and was replaced by that
    comparison. The ITLB `abort()` is dropped as upstream did (C-4322, a
    decision a human may overturn; unobservable in this boot). Also fixed:
    `--check-version` now applies cumulatively (it reported 5/7 for 8.2.10's
    own series, C-4325) and the scripts ask for `-d invalid_mem` on QEMU
    >= 10 (C-4323). EXP-2026-11-21-M8.A9-qemu-11-port.

- [x] **M8.A8 — F0 EXP + register table** in `docs/format/firmware.md`.
  - Status: done · Owner: task/m8.a8-f0-exp-registers · Critical: no
  - Depends: M8.A3, M8.A6 (M8.A4/M8.A5 merged, archived 2026-11-06)
  - Precheck: `-M ze0` boots EU2011 past F1 (M8.B5) and `dbgmsg` exists
    (M8.B6); F0 per `docs/research/full-system-emulation.md` §4.
  - Scope: one EXP, `tools/ze0_regs.py`, one section in
    `docs/format/firmware.md`; no QEMU patch.
  - Goal: record stage F0 and write down what `-M ze0` models and what the
    boot still touches outside the models.
  - Done when: (made concrete 2026-11-20) an EXP records an EU2011 boot
    with kernel debug text on serial port 0, MMUCR.AT = 1 and 0 hits on the
    halt/unhandled-exception paths, with a negative control; and
    `firmware.md` has a table of modelled windows (address, size, reset
    value, read from) plus the registers the boot touches unmodelled.
  - Stop: if F0 fails, record the first fault and the register behind it
    instead of the table of unmodelled registers.
  - Result: EXP-2026-11-20-M8.A8-f0-registers (C-1300–C-1304). F0 reached:
    150 s boot, 23 896 B / 548 lines on serial port 0, MMUCR `0xfc00b801`,
    0/0 fault-path hits; `dbgmsg=0` gives 0 B with 176 sink calls.
    `firmware.md` § "ze0 register table": 18 modelled windows and 177
    unmodelled registers on 25 pages (148 on-chip, all via the area-7
    alias; DMAC/HPB DMAC and IOLIB.dll blocks lead). New tool
    `tools/ze0_regs.py` (`census`, `who`).
  - Claims: C-1300–C-1309

- [x] **M8.B2 — TMU** (`0xffd80000`, `0xffd81000`, `hw/timer/sh_timer.c`).
  Done when `CurMSec` advances.
  - Status: done · Owner: task/m8.b2-ze0-tmu · Critical: no
  - Depends: M8.B1
  - Done when (made concrete 2026-11-20, the original line is kept above):
    on `-M ze0 -kernel archive/head256.img`, EU2011 `CurMSec`
    (`0x89e41888`) sampled over HMP makes a jump of at least 1000 ms, and
    `ze0_tmu.py rate` puts (CurMSec delta / 1000) per host second within
    [0.98, 1.02]. Negative controls: `-M ze0,tmu=off` (no TMU) leaves
    `CurMSec` without such a jump; the old 60 MHz clock gives a ratio
    outside the band. Also: two `-icount` boots give the same exception
    sequence, interrupts included.
  - Result: EXP-2026-11-20-M8.B2-ze0-tmu (C-1320–C-1323). Patch
    `tools/qemu-ze0/patches/ze0-0005-hw-sh4-ze0-tmu-clock.patch`: Pphi
    42 MHz from the OAL count rate 2 625 000 Hz (`0x88004cf8`, TPSC Pphi/16),
    option `tmu=off`. `CurMSec` jumps by the max period 818 088 ms after
    818.0 host s (ratio 1.0001); 60 MHz gives 1.43, `tmu=off` stays 0;
    two `-icount shift=0,sleep=off` boots are identical. TMU ch3–5 unused.
    The kernel ends in its `Halting system` loop (`0x88022170`), so
    `OEMIdle` is not reached (M8.B5). Tool: `tools/ze0_tmu.py`.
  - Claims: C-1320–C-1329

- [x] **M8.B5 — Milestone F1**: `filesys.exe` and `device.exe` start, 60 s
  without a fault.
  - Status: done · Owner: task/m8.b5-ze0-f1-filesys · Critical: no
  - Depends: M8.B1, M8.B2
  - Done when (made concrete 2026-11-20, before the controlled runs; the
    original line is kept above): one `-M ze0 -kernel archive/head256.img
    -icount shift=0,sleep=off` boot under `tools/ze0_dbgmsg.py run`
    (debug-string hook `0x880404f4`, EU2011) ends with (1) `ze0_dbgmsg.py
    modules` on a RAM dump of `0x89e40000`+256 KiB listing `filesys.exe`
    and `device.exe`; (2) 0 hits at `0x88011cb8` ("Unhandled exception")
    and `0x88022164` ("Halting system"), and no `Exception` line in the
    kernel's debug output; (3) `CurMSec` (`0x89e41888`) ≥ 60 000 at the
    end. Negative controls: `ext-ram=off` and the M8.B2 binary (no
    odd-PC address error) must fail (1) or (2).
  - Result: EXP-2026-11-20-M8.B5-ze0-f1-filesys (C-1350–C-1354). Patch
    `ze0-0006-sh4-iaddr-error-ze0-ext-ram.patch`: an odd-PC fetch raises
    the SH-4 address error 0x0e0 (the CE API trap; QEMU raised 0x180, the
    kernel's "Unhandled exception c000001d" → `Halting system`), and the
    OAL's second 128 MiB DRAM at phys `0x10000000`. `filesys.exe` and
    `device.exe` start (RAM loader records + their debug text), 839 s of
    guest time, no unhandled exception; `ext-ram=off` and the M8.B2
    binary fail. Next blockers: SD host (launcher `SD Check Error`,
    M8.C10), OEM IOCTLs, `gwes.exe` not started. Tool:
    `tools/ze0_dbgmsg.py` (kernel debug text over the gdbstub).
  - Claims: C-1350–C-1359

- [x] **M8.E2 — Registry as loaded** (`boot.hv`, `default.hv`, `user.hv`):
  driver list, `IoBase`, `Irq`, load order. Two routes: static hive parser
  after M1.4, or a RAM dump after M8.B5. Done when the driver table is in
  `firmware.md`.
  - Status: done · Owner: task/m8.e2-registry-loaded · Critical: no
  - Depends: M1.4, M8.B5 (either route: static hive parser or RAM dump)
  - Claims: C-1610–C-1619
  - Result: EXP-2026-11-20-M8.E2-registry-loaded; C-1610–C-1616 (C-1617–C-1619 reserved). Static route: new `tools/ce_drivers.py` decodes `boot.hv`/`default.hv` in memory (M1.4 kernel decode) and joins `Drivers\Launch` keys to M1.34's `AppLaunch.dll` records. EU2011 build B (`archive/head256.img`, `92aa525d…`): 9 `Drivers\BuiltIn` drivers (all `Order 0`, last `AppLaunch.dll`) + 63 `Drivers\Launch` keys = launch records #7–#69 (62 matched; load order = record index + waits, not hive `Order`); only `OHCI` (`MemBase 0x099a1000`, `SysIntr 0x1c`) and `WaveSSI1/2` (`SysIntr 0x24/0x25`) carry resources, no driver has `IoBase`/`Irq`; build C same 72 keys (table lacks `UART3`); US2011 build B identical. Table in `docs/format/firmware.md`.

- [x] **M9.5 — Runner `run` end-to-end**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: M9.2 or M9.4, M9.3
  - Goal: `runner.py run FUNC --input FILE [--engine ghidra|qemu] --json`
    with targets in `tools/l3_harness/targets.json`.
  - Done when: one target runs end-to-end and prints `accepted`, return
    value, stub log, digests.
  - Result: `runner.py run` executes `probe-zlib-cmf` end-to-end on PySh4 with
    the stub dispatcher, emitting ACCEPT/MISMATCH/BLOCKED/SKIP and a stub call
    log (EXP-2026-11-06-M9.5-runner); pipeline result, not a reader verdict.
  - Claims: C-1670–C-1679

- [x] **M1.33 — M1.22's census and relocated-body tables come from an uncommitted script, and its Method has ellipses**
  - Status: done · Owner: task/m1.33-census-command · Critical: no · Pair: required
  - Result: `cerom.py modules --census archive/head256.img archive/us256.img` prints `EU 149 / US 151 / common 148 / only-EU 1 / only-US 3 / code-identical 1 / code-different 147` and `fn_match.py bodies archive/head256.img archive/us256.img --fixture-rows tools/fixtures/fn_match_eu_us_2011.json --negative 0x003fbed8:0x00424850` reproduces all 12 relocated-body rows + the rewrite control; the M1.22 Method block has 0 ellipses; C-3530–C-3532 cite the commands; two prose-only numbers (chunk engine past-body index 878, the halfword-65 variant) are not reproduced (C-4232). EXP: `docs/experiments/EXP-2026-11-19-M1.33-census-command.md`. Claims C-4230–C-4232.
  - Depends: M1.22 (done), M1.22b (done), M1.31 (done — the leaf census is the shape to copy)
  - Goal: put M1.22's module census and relocated-body table behind committed commands (`cerom.py modules --census`, a `--selftest`-covered table printer) and drop the EXP's ellipses, so C-3530–C-3532 are reproducible by anyone.
  - Note (SE 2026-11-17): the M1.22 EXP publishes `EU modules 149, US modules 151, common 148`, `code-identical: 1`, `code-different: 147`, and a 12-row `body EU=n US=n first masked diff: NONE` table. I reproduced the census by hand (my own throwaway script; the module deltas match C-3530 exactly: only-EU `RDSCC.dll`, only-US `RBDS_CC.dll`/`XMCC.dll`/`XMStatusCC.dll`, 148 common), so the numbers are right — but no committed tool prints them, so a later reader cannot re-run them, and the EXP's Method uses `--cmp …/POINT010.DAT.cmp` / `archive/us256.img …` ellipses, which TEMPLATE.md's "no ellipsis" rule forbids. C-3530/C-3531/C-3532 cite a command that lives only in the session.
  - Precheck: `grep -nE '^ *python3 tools/.*\\.py .*…' docs/experiments/EXP-2026-11-17-M1.22-us-build-census.md` prints at least four elided commands; `python3 tools/cerom.py --image-start 0x200200 archive/head256.img modules | wc -l` is `149` and the US head `151`, but no `tools/*.py` subcommand prints `common 148` or the relocated-body table.
  - Scope: one tool only — extend `tools/cerom.py` with `modules --census <EU> <US>` (names the only-EU/only-US/common sets and the per-module EXECUTE-section SHA-256 `identical/different` counts) and `tools/fn_match.py` (or a `tools/build_census.py` with `--selftest`) for the pool-masked relocated-body table; then replace the EXP's four ellipsis command blocks with the committed commands. Not: a new US VA (M1.32), not the 13-VA fixture (M1.28), not the EXP's prose beyond the commands.
  - Input: `tools/cerom.py` (`modules`, `sections`), `tools/fn_match.py` (`code_digest`, `leaf_words`, the pool masking), `docs/experiments/EXP-2026-11-17-M1.22-us-build-census.md`, `archive/head256.img` / `archive/us256.img`.
  - Hints: the census is a *set* operation on `modules` plus a per-module section hash loop — reuse `cerom.sections`, do not re-parse `ROMHDR`. The relocated-body table is already the `fn_match` masked-form comparison with pool slots zeroed; expose it rather than copy the loop. A `--selftest` must build two synthetic module lists and prove `common/only-EU/only-US` plus the identical/different split without an image.
  - Done when: `python3 tools/cerom.py modules --census archive/head256.img archive/us256.img` prints `EU 149 / US 151 / common 148 / only-EU 1 / only-US 3` and the `code-identical 1 / code-different 147` split (or the EXP is corrected with the command that contradicts it); the relocated-body table is printed by a committed command; `grep -c '…' EXP-…-M1.22` over the Method block is 0; `selftest.py --only cerom` and `--only fn_match` pass; C-3530/C-3531/C-3532's evidence cells name the new commands.
  - Stop: if the per-module section hash needs a decompressor for one build, restrict the census to uncompressed EXECUTE sections, say so in the claim, and do not claim 0 compressed sections beyond what `va_class.py` prints.
  - Falsifier: the committed census prints a different module delta than C-3530, or a committed command cannot reproduce one row of the relocated-body table.
  - Claims: C-4230–C-4239

- [x] **M9.32 — Reconcile M9.11: `cmp_ind_reader` meets done-when or block precisely**
  - Status: done · Owner: task/m9.32-reconcile-m9.11 · Critical: yes · Pair: required
  - Depends: M9.11, M9.11b
  - Goal: close the M9.11 reopen cleanly: M9.11b registered `cmp_ind_reader` as `firmware_call` with declared sec1 `inflate_mask[17]` provenance, but M9.11 remains open with stale precheck/scope text and its done-when requires all three POINT010 pairs + controls through the firmware path/target.
  - Precheck: `python3 tools/chunk_decoder_l3.py --selftest` and `python3 tools/l3_harness/runner.py --selftest` (or bounded equivalent) pass; `targets.json` contains `cmp_ind_reader` `firmware_call` with `sec1_table`; factory/S1/S2 POINT010 pairs available per rule 11 (M5.13b tree or fetchable inputs).
  - Scope: verify M9.11 done-when end-to-end: for factory, S1, S2 pairs page `0x840ba0` byte-identical to `cmpind.py extract` via the registered runner target (or documented equivalent that exercises the same registered path for all pairs), plus corrupt-`.ind` and swapped `+4`/`8` controls as in EXP-2026-11-08-M9.11-chunk-decoder. Update M9.11 task text (precheck/scope/note) to reflect M9.11b. No new format claims.
  - Input: `tools/l3_harness/runner.py`, `targets.json`, `tools/chunk_decoder_l3.py`, `tools/cmpind.py`, EXP-2026-11-08-M9.11-chunk-decoder, EXP-2026-11-08-M9.11b-firmware-call-target, M5.13b S1/S2/factory pairs.
  - Done when: M9.11 is `done` with `Result:` naming an EXP that records all three pairs + controls passing through the registered target/path and cites sec1-table provenance, OR M9.11 is `blocked` with the exact missing pair/control/runner gap and `Unblock:` named. No stale "no firmware-call entry kind" text remains in M9.11.
  - Stop: if S1/S2 corpora are unavailable and cannot be obtained by existing tools, block with missing corpus named (do not claim all-pairs pass on factory only).
  - Result: EXP-2026-11-19-M9.32-reconcile-m9.11; C-3370–C-3375. All three pairs + both controls through the registered `cmp_ind_reader` path with declared sec1 provenance were first satisfied by EXP-2026-11-09-M9.11-closeout-cmp-ind-reader (C-2157); this task re-measured them (linkage: M9.34). M9.11 stays `done`: re-measured from the US card, `runner.py run cmp_ind_reader` (EU2011) returns page `0x840ba0` byte-identical for factory/S1/S2 and passes both controls. Found and fixed one runner gap: the `firmware_call` path ignored the target `build`, so `cmp_ind_reader_us2011` always ran EU VAs and BLOCKED; it now routes the build (and refuses a mismatched `entry.va`), and the US target passes the same 3 pairs + 2 controls. S2 rebuilt with zlib 1.3 (`b4ef43b9…`, not the pinned `c2b9c388…`).
  - Claims: C-3370–C-3379

- [x] **M9.33 — Map reopened L3 target rerun prerequisites (M1.2f / M9.24 / M9.28 / H45)**
  - Status: done · Owner: task/m9.33-rerun-prereqs-map · Critical: no · Pair: solo
  - Result: EXP-2026-11-20-M9.33-rerun-prereqs-map; C-3400–C-3404. Every named target has a verdict. M9.6, M9.11, M9.13, M9.14 and M9.17 are done with runs (`READY`; the last three run through `datask_l3.py`/`vcard_l3.py`/`mmain_l3.py`, so their `runner.py` entries stay `blocked` by design). M9.10 is `READY`: US VAs, accessor and byte order are all met, and only its own runner and M9.55's `l3check` row remain. No target waits on M1.2f/M1.19, M9.28 or M9.24. `l3_precond` gaps (cross-build VA classes, no "runs elsewhere" state) → new M9.59.
  - Depends: H45, M9.28
  - Note (M9.28, 2026-11-19): the input-buffer prerequisite is **cleared** — `entry.input_region` maps a file-derived page at a chosen VA (EXP-2026-11-19-M9.28-input-region, C-3210–C-3219); remaining blockers for the reopened readers are sec1 `INIT` bytes (M1.2f) and import/CRT binding (M9.24).
  - Goal: make "re-run reopened L3 reader targets" cheap to decide: for M9.6/M9.10/M9.13/M9.14/M9.17/M9.11 (open states), state which blockers are cleared (M9.20/M9.11b/M3.20) and which prerequisites remain (sec1 decompression M1.2f, import/CRT/file binding M9.24, input-buffer mapping M9.28, reader VA/signature evidence), using H45 verdicts where available.
  - Precheck: `test -f tools/l3_precond.py` or the H45-delivered tool exists and `--selftest` passes (else task becomes `blocked` on H45 with that named).
  - Scope: docs/planning output (EXP or a small table update in `docs/research/reader-coverage.md` notes / TODO task notes, named in PR) — no firmware execution, no silent PASS. Keep rule 13: verdict tables are planning aids, not L3 results.
  - Input: H45, M9.28, targets.json, reader-coverage matrix, EXPs for M9.6/M9.11/M9.13/M9.14/M9.17, M1.2f/M9.24 task texts.
  - Done when: each reopened/blocked L3 reader target above has an explicit `READY|BLOCKED|UNKNOWN` prerequisite verdict with missing dependency IDs (or "H45 unavailable") recorded in an EXP; TODO/coverage notes reference it. No target is marked runnable without evidence.
  - Stop: if H45 is unavailable and target metadata is insufficient, record `UNKNOWN` with missing fields and stop (do not guess).
  - Claims: C-3400–C-3409

- [x] **M9.34 — Close M9.32 as satisfied by M9.11 closeout (board/EXP linkage)**
  - Status: done · Owner: task/m9.34-close-m9.32-link · Critical: no · Pair: solo
  - Result: EXP-2026-11-19-M9.34-close-m9.32-link. M9.32 was already `done` (PR #253); every done-when element (factory/S1/S2, corrupt-ind, swap-4-8, registered `cmp_ind_reader`, declared sec1 `0x574de0`) maps to EXP-2026-11-09-M9.11-closeout and is re-observed on EU2011+US2011 in the M9.32 EXP. Only change: M9.32's `Result:` now cites the closeout EXP. 0 stale blocker lines in M9.11/M9.32; no new claims (C-3430–C-3439 unused).
  - Depends: M9.32, M9.11, M9.11b
  - Goal: remove stale L3-board state now that M9.11 closeout has satisfied M9.32's done-when; keep evidence explicit without duplicating claims or re-running vendor-image checks unnecessarily.
  - Precheck: `test -f docs/experiments/EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md`; confirm M9.11 is `done` with Result naming that EXP and M9.32 is still `open`; `python3 tools/claims_check.py` and `python3 tools/todo_check.py` pass.
  - Scope: TODO status/text reconciliation for M9.32 (and only stale precheck/scope wording in M9.11 if still misleading, keep edits minimal/local). No new firmware execution, no format claims, no vendor bytes.
  - Input: EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md, EXP-2026-11-08-M9.11-chunk-decoder.md, EXP-2026-11-08-M9.11b-firmware-call-target.md, TODO M9.11/M9.32 blocks.
  - Done when: M9.32 is `done` or `blocked` with `Result:` that cites the M9.11 closeout EXP as satisfying all three pairs + controls through the registered `cmp_ind_reader` path with declared sec1 provenance; M9.11/M9.32 contain no stale "not registered"/"no firmware-call entry kind" blocker text except accurate history; `todo_check.py` and `claims_check.py` pass.
  - Stop: if the closeout EXP does not actually cover a M9.32 done-when element (pair/control/runner path/corpus availability claim), record the exact gap and keep M9.32 `blocked` naming it — do not close on incomplete evidence.
  - Claims: C-3430–C-3439

- [x] **M9.37 — Decoder audit: every instruction form PySh4 models, tested with distinct registers and compared with `sh4dis.py`**
  - Status: done · Owner: task/m9.37-decoder-audit · Critical: yes
  - Depends: —
  - Goal: three decode defects survived five days of L3 work because the engine's own tests used operand values that hide a register mix-up (`n == 0`, `m == 0`). Make that class of defect impossible to miss, and know which opcodes of the firmware the engine cannot run at all.
  - Precheck: `python3 tools/l3_harness/engine.py --selftest`; `python3 tools/sh4dis.py --selftest`.
  - Scope: (1) a table-driven selftest: for each modelled form one case where `Rn`, `Rm` and `R0` are three different registers holding three different values, and the expected effect is written from the SH-4 manual encoding (`nnnn` = bits 11–8, `mmmm` = bits 7–4, the 0x8xxx forms have `Rn`/`Rm` in bits 7–4); (2) a differential check: for every distinct opcode in the pdata-covered code of `Navi.exe` and `nk.exe`, the engine's decode class and operand registers equal those of `tools/sh4dis.py` (two independent tables); (3) a census: opcodes present in the firmware that the engine raises `IllegalInstruction` for, with counts. Floating point may stay unmodelled, but counted.
  - Input: `tools/l3_harness/engine.py` (`_exec_*` dispatch), `tools/sh4dis.py`, `binutils-sh4-linux-gnu` `objdump -b binary -m sh4 -EL` as a third opinion where the two tables disagree.
  - Hints: the H51 defects were in `_exec_branch8` (0x80/0x81) and `_exec_misc` (`pattern = insn & 0xF0FF` matched `mul.l` only when `Rm = r0`). Look at every `pattern ==` comparison in `_exec_misc`/`_exec_system` for the same mistake, and at `mac.l`/`mac.w`, `div1`, `rotcl/rotcr`, `addc/subc/negc` T-flag handling — the decompressor and zlib exercise only part of them.
  - Done when: the selftest has one distinct-register case per modelled form; the differential check reports 0 disagreements or each one is fixed/explained; the census is in the EXP; the M9.36 targets still pass.
  - Stop: an opcode family that needs FPU or MMU state is listed as out of scope.
  - Claims: C-3590–C-3599
  - Result: `docs/experiments/EXP-2026-11-19-M9.37-decoder-audit.md` (C-3590–C-3597). `decode_audit.py compare` reports 0 disagreements / 0 executor drift over 28,198 (EU Navi), 11,321 (EU nk), 28,151 (US Navi) MODELLED distinct opcodes; `census` buckets every other opcode (FPU/MMU/IN_SCOPE_UNMODELLED/TRAP) with counts. Added an independent `DECODE_TABLE`/`decode_fields` + drift test, structured `sh4dis` operands, distinct-register selftest, and modelled mac.l/mac.w/div0s (div1 stays in-scope-unmodelled). Fixed an exact-opcode mask defect (`0x0918` ran as `sett`). `div1` (513 EU Navi insns) needs M/DIV state; the follow-up M9.48 can model it if a target needs it.

- [x] **M9.40 — `chunk_decoder_l3 --build` names the US `inflate_mask` in C-3535, but the run maps a constant**
  - Status: done · Owner: task/m9.40-us-mask-read · Critical: no · Pair: required
  - Depends: — (M1.22's `--build` selector and US table are on `main`)
  - Goal: M9.11b found the EU `inflate_mask[17]` by deriving it from `inflate`'s own `shll2` load, and M1.22 added a US `BUILD_TARGETS["us2011"]["inflate_mask"] = 0x005987B0`; C-3535 then says the US run uses "the US `inflate_mask` from the unique `shll2; …` site". That US value is used, but the [17] table is **written**, not read: `chunk_decoder_l3.run()` puts the public zlib `2^n - 1` series at the build's VA, so no firmware byte and no harness assertion proves the US and EU VAs actually hold that table. The verdict (byte-identical decode) is sound; the provenance sentence in C-3535 overstates what was verified.
  - Precheck: `sed -n 242,252p tools/chunk_decoder_l3.py` shows `inflate_mask` written from `(1 << n) - 1`, not read from the image; `python3 tools/chunk_decoder_l3.py --selftest` passes; `python3 tools/chunk_decoder_l3.py run archive/us256.img … --build us2011` prints `verdict: PASS` (the run this provenance must not change).
  - Scope: `tools/chunk_decoder_l3.py` (a `--read-mask` path that loads the table from the image at the build's VA and fails if it differs from `2^n - 1`, or an explicit `OBSERVED not read` in the log), the C-3535 wording, and the M1.22 EXP's mask sentence. No verdict change, no new firmware search, no EU target change.
  - Input: `tools/chunk_decoder_l3.py` (`BUILD_TARGETS`, the `zero-mask` branch at ~line 242), `tools/cerom.py` (`va2file`) or `tools/va_class.py` to map the VA, C-3535, EXP-2026-11-17-M1.22-us-build-census.
  - Hints: the two VAs may both be `INIT`/BSS (H49: 94 % of compressed sec1 is zero) — if so, the honest result is "the value cannot be read; the mask is the public zlib constant written at the build's own slot", and C-3535 loses the "from the US site" clause. Do not turn a write into a read to make the claim true.
  - Done when: the log line says whether the mask was **read** from the image or **written** from public zlib, per build; a negative control (a deliberately wrong series at the US VA) either fails the read or is reported as `OBSERVED (not read)`; C-3535 and the EXP say only what the run did; `--selftest` and `python3 tools/gate.py` green; the EU/US decode verdicts are unchanged.
  - Stop: if `va_class.py` says both mask VAs are `INIT`, record `OBSERVED: mask is written (public zlib), VA is INIT` and stop — M1.19 is the task that makes them readable, not this one. If C-3535's edit would re-open an M1.22 claim, keep M1.22's wording as printed at `3d79bcc` and mark the correction `Superseded by` this task's EXP instead of editing a done row.
  - Falsifier: C-3535 still claims the US mask was taken from the image after the change, or the change alters either build's decode verdict.
  - Result: EXP-2026-11-19-M9.40-us-mask-read; C-4180–C-4184. Both mask slots are `INIT`, but readable: `chunk_decoder_l3.py run --sec1 read-mask` decodes `Navi.exe` sec1 with `nk_decomp` and reads 17 words equal to `2^n - 1` at US2011 `0x005987b0` and EU2011 `0x00574de0`; `zero-mask` now logs `WRITTEN … OBSERVED (not read)`. Verdicts unchanged (US POINT010 on US `insns=1057251` PASS; EU POINT010 on both builds `insns=1957314` PASS, read and written alike). Negatives: one planted word in a US sec1 dump and each build's VA on the other image fail the read. C-3535 already said "writes"; left as printed.
  - Claims: C-4180–C-4189

- [x] **M9.45 — PySh4 ten times faster, measured on the decompressor**
  - Status: done · Owner: task/m9.45-pysh4-speed · Critical: no · Pair: solo
  - Result: EXP-2026-11-20-M9.45-pysh4-speed; C-5320–C-5324. `PySh4.run_until` runs translated blocks (per-site memory caches, registers in locals, shared compiled code). `Navi.exe` sec1: `run_until` 25.89 s → 2.54 s median under load (10.2×; 10.7× at load 2.5), CPU 9.1×, SHA-256 unchanged; `check` 245/245 byte-identical JSON, user 5 m 23 s → 27 s. New differential selftests (all 65,536 halfwords in `--full`, random blocks with SMC/stops/budgets). Overriding engines (`GuardedPySh4`, `ShimSh4`) stay stepped.
  - Depends: M9.37 (the decoder audit is the regression suite for this change)
  - Goal: PySh4 runs about 260,000 instructions per second (H51: 183,114 instructions in 0.7 s). `nk_decomp.py check` takes ten minutes, and anything longer than one reader function is out of reach. Whole-task emulation (M9.44's mount machine, later a headless `Navi.exe` map task) needs an order of magnitude.
  - Precheck: `time python3 tools/nk_decomp.py section IMG256 --module Navi.exe --index 1` (about 16 s; the output SHA-256 is in EXP-2026-11-11-H51).
  - Scope: `tools/l3_harness/engine.py` only. A predecode cache (opcode at VA → bound handler with operands extracted once, invalidated on a write to an executable region), register file as a list instead of a dict of names, memory regions found by bisect with a last-hit cache. No change of behaviour; no C extension (stdlib rule).
  - Input: `python3 -m cProfile -s cumtime tools/nk_decomp.py section …` first — optimise what the profile shows, not the list above.
  - Done when: the benchmark is ≥ 8× faster with the same output SHA-256; `engine.py --selftest`, `selftest.py` and the M9.36 table are unchanged; the EXP has the profile before and after.
  - Stop: at 3× with the profile flat, record it and stop.
  - Claims: C-5320–C-5324 (block C-5320–C-5329)

- [x] **M9.48 — Model `div1`, the last integer form the engine rejects**
  - Status: done · Owner: task/m9.48-pysh4-div1 · Critical: no · Pair: solo
  - Result: EXP-2026-11-19-M9.48-pysh4-div1; C-5180–C-5185. `div1` modelled from the manual's DIV1 code; `div0s` corrected (M9.37 used SR bits 2/1 and T=0; now Q=bit 8, M=bit 9, T=!(M==Q)), `div0u` clears M/Q. Census: `div1` MODELLED on EU Navi 513, EU nk 217, US Navi 860; `compare` 0/0 on all three; `div1_l3.py isolate` shows only div0s/div0u/div1 changed vs `8e3b99f`. The firmware's own nk.exe udiv/urem/sdiv/srem (`0x88040b6c`/`0x88040c18`/`0x88042594`/`0x88040988`) match C on 20 pairs; an M/Q-blind div1 matches none. Follow-ups M9.49 (`mac.w` NameError), M9.50 (`rotcl`/`rotcr`).
  - Depends: M9.37 (the decoder audit is its regression suite and census)
  - Goal: `decode_audit.py census` leaves `div1` (`0x3?4`) as the only IN_SCOPE_UNMODELLED integer form: 513 EU and 217 nk instructions, counted but not runnable. It needs the M/Q bits and the divide step, not just T, so the H51-era tests never covered it.
  - Precheck: `python3 tools/l3_harness/decode_audit.py census archive/head256.img Navi.exe --image-start 0x200200` prints `div1=513` with verdict `in-scope-unmodelled`; `engine.py --selftest` passes.
  - Scope: `_exec_store` sub `0x4` (`div1 Rm,Rn`) and `_exec_alu` `div0s`/`div0u` M/Q handling in `tools/l3_harness/engine.py`; one distinct-register row plus a two-step `div0s;div1` control per sign case. No FPU/MMU, no decoder-table change.
  - Input: the SH-4 manual divide-step pseudocode; `tools/l3_harness/decode_audit.py` (bucket moves IN_SCOPE_UNMODELLED → MODELLED).
  - Done when: `div1` moves to MODELLED in the census (EU Navi 513, nk 217 instructions), `compare` still reports 0 disagreements / 0 drift, and `engine.py --selftest` has a div1 row that fails if M/Q are ignored.
  - Stop: if the semantics cannot be pinned from the manual in one pass, keep it bucketed and record the negative rather than guessing.
  - Claims: C-5180–C-5185 (C-5186–C-5189 handed to M9.49/M9.50)

- [x] **M9.49 — `mac.w @Rm+,@Rn+` crashes the engine with a host `NameError`**
  - Status: done · Owner: task/m9.49-pysh4-macw · Critical: no · Pair: solo
  - Result: EXP-2026-11-19-M9.49-pysh4-macw; C-5300–C-5304. `mac.w` defines `rm` and follows the manual's MACW (also fixed: words were multiplied as 32-bit register images, n == m read one address twice, S = 1 saturation ignored). `isolate --before 9a9c3cf --expect mac.w` → only `mac.w` (224 halfwords); `compare` 0/0 on EU Navi (28,373), EU nk (11,360), US Navi (28,323). `decode_audit.classify()` maps a probe data page and buckets host exceptions as unmodelled: on the pre-fix engine it now reports 17/1/14 drift. New task M9.51 (`mac.l` is modelled as a register form).
  - Depends: M9.48 (its `div1_l3.py isolate` found it)
  - Goal: `_exec_system`'s `mac.w` arm reads `rm`, which `_exec_system` never defines, so every `mac.w` whose `@Rn` load succeeds raises `NameError` instead of running (224/256 halfwords in M9.48's first `isolate` state). `decode_audit.classify()` hides it because its probe faults on the unmapped `@Rn` first, so C-3593 counts `mac.w` (54 EU Navi insns) as modelled.
  - Precheck: map memory at `r1`/`r2`, `_execute(0x412F)` on `PySh4` raises `NameError: name 'rm' is not defined`.
  - Scope: define `rm` in the `mac.w` arm of `tools/l3_harness/engine.py` (Rm is bits 7-4), a distinct-register `mac.w` row with mapped memory in `engine.py --selftest`, and `decode_audit.classify()` mapping a probe page so a host exception is not mistaken for MODELLED. No other instruction.
  - Done when: the selftest row passes and fails on the unfixed engine; `div1_l3.py isolate --before <pre-fix engine>` lists only `mac.w`; `decode_audit.py compare` stays 0/0 on EU Navi, EU nk, US Navi.
  - Claims: C-5300–C-5309 (was C-5186–C-5187; fresh block for this run)

- [x] **M9.50 — Model `rotcl`/`rotcr` so the `nk.exe` divide routines run in the bare engine**
  - Status: done · Owner: task/m9.50-pysh4-rotcl · Critical: no · Pair: solo
  - Depends: M9.48
  - Result: EXP-2026-11-19-M9.50-pysh4-rotcl; C-5310–C-5314. `rotcl`/`rotcr` modelled in the engine (and named in `sh4dis`); `div1_l3.py run archive/head256.img nk.exe` → `4/4 runnable functions match` with `rotcl(shim)=0 rotcr(shim)=0` (EU2011 and US2011); `isolate --before cc15728 --expect rotcl,rotcr` → only rotcl (16) / rotcr (16); `compare` 0/0 on EU Navi (28,394), EU nk (11,374), US Navi (28,345). `rotl`/`rotr` stay unmodelled (30/1, 6/8, 38/1 insns).
  - Goal: the firmware's 32-bit divide routines (EU2011/US2011 `nk.exe` `0x88040b6c`, `0x88040c18`, `0x88042594`, `0x88040988`) interleave `div1` with `rotcl` (`0x4n24`) and use `rotcr` (`0x4n25`); the engine rejects both, so M9.48 ran them through a tool-local shim in `div1_l3.py`. Any L3 target that divides through these helpers stops at the first `rotcl`.
  - Scope: `rotcl`/`rotcr` in `_exec_system` plus `DECODE_TABLE` rows, a distinct-register selftest row each, and `div1_l3.py run` without the shim (keep the shim count at 0 as the check). No FPU.
  - Done when: `div1_l3.py run archive/head256.img nk.exe` prints `4/4 runnable functions match` with `rotcl(shim)=0 rotcr(shim)=0`; `isolate --before <pre-change engine>` lists only `rotcl`/`rotcr`; `compare` 0/0 on the three corpora.
  - Claims: C-5310–C-5319 (was C-5188–C-5189; fresh block for this run)

- [x] **M9.51 — `mac.l` is modelled as `mac.l Rm,Rn`; the SH-4 form is `mac.l @Rm+,@Rn+`**
  - Status: done · Owner: task/m9.51-pysh4-macl · Critical: no · Pair: solo
  - Result: EXP-2026-11-20-M9.51-pysh4-macl; C-5630–C-5634. `mac.l` now reads `@Rn`/`@Rm` longs with post-increment and S = 1 48-bit saturation; `isolate --before 6512c1b --expect mac.l` → only mac.l (256); `compare` 0/0 on the three corpora. New `tools/l3_harness/arm_census.py`: none of 11 documented L3 runs (31.7 M instructions) executes `mac.l`, so no L3 verdict changes. The M9.45 fast path has no `mac.l` template; `_step` runs it.
  - Depends: M9.49
  - Goal: `engine.py`'s `0x0nmF` arm multiplies the two *register values*; the manual's `0000nnnnmmmm1111` is `MAC.L @Rm+,@Rn+` (two memory longs, both pointers +4, S = 1 saturates at 48 bits). The census counts 4,164 EU2011 Navi / 189 EU2011 nk / 4,839 US2011 Navi `mac.l` as modelled with wrong semantics (C-5304); the M9.37 selftest row checks the register form.
  - Scope: the `mac.l` arm and its selftest row in `tools/l3_harness/engine.py` (manual MACL code: distinct registers, n == m, S = 0/1, fault before register writes); first `grep` the L3 targets for a run that executed `mac.l` and say whether any result changes. No other instruction.
  - Done when: the new row fails on the current engine and passes after; `div1_l3.py isolate --before <pre-change engine> --expect mac.l` lists only `mac.l`; `decode_audit.py compare` 0/0 on EU Navi, EU nk, US Navi.
  - Precheck: `grep -n "mac.l Rm,Rn" tools/l3_harness/engine.py` finds the register-form arm (if it is gone, the task is moot).
  - Stop: if an L3 result depends on the register-form `mac.l`, record which and set `blocked` on the owning task's re-run instead of changing two things at once.
  - Claims: C-5630–C-5634 (block C-5630–C-5639)

- [x] **M9.55 — Run the US POI walk from `runner.py` and register the target so `l3check` reports its verdict**
  - Status: done · Owner: task/m9.55-us-poi-runner · Critical: yes · Pair: required
  - Depends: M1.22 (done — US VAs), M1.22b (done — `build` field), M9.42 (done — the wrong-build verdict is clean)
  - Note (M9.41, 2026-11-20): the US `point_walk_l3 walk --build us2011` run this task ports **already exists** (C-4221 is evidence, not a dependency), so no open task gates it — only the `runner.py` registration remains. The M9.39 mutant page is the positive witness, never a negative control (C-4178).
  - Goal: M9.41 showed the walker runs (factory + M9.39 mutant PASS, wrong-build FAIL) but cannot be a `l3check --build-corpus` row from `targets.json`/`TARGET_EVIDENCE` alone: `runner.py` has no POINT `firmware_call` program (`unknown firmware_call program 'point_walk_v1'`) and corpus mode supplies no `--image/--cmp/--ind`, so a Scope-sized target is BLOCKED (EXP-2026-11-20-M9.41-us-poi-row, C-4223–C-4225). Port the walk into `runner.py` as a registered program and plumb the walker inputs, so the row reports a verdict.
  - Precheck: `python3 tools/point_walk_l3.py walk archive/us256.img --cmp <US POINT010.DAT.cmp> --ind <…ind> --page 0x840ba0 --page-len 42848 --build us2011` prints `result: PASS`; `python3 tools/l3_harness/runner.py run point_walk_us2011 --targets <scratch targets.json> …` today prints `BLOCKED: unknown firmware_call program 'point_walk_v1'` (the gap).
  - Scope: `tools/l3_harness/runner.py` (a `point_walk_v1` `firmware_call` program that calls `point_walk_l3.run_nth`/`run_skip` with the target's build, refusing a wrong build as `result: FAIL`, M9.42 shape), `tools/l3check.py` (corpus-mode `--image/--cmp/--ind` pass-through and the `TARGET_EVIDENCE` row), `tools/l3_harness/corpus.py` (an optional POINT010 page entry), and `tools/l3_harness/targets.json` (`point_walk_us2011`, `build: us2011`, VAs read through `build_targets.py`, not retyped). Update M9.10's Status/Result to cite the row. No new VA; no writer change; no map-format claim.
  - Hints: the walker VAs are already the single-owner map (`build_targets.py show`, `point_walk_l3`); reuse `point_walk_l3.load_page`/`run_nth` rather than re-deriving the page swap. The M9.39 mutant page is the positive witness (`n=501 +4`), never a negative control (C-4178/C-4435). Keep `l3check --selftest`'s `total` in step with any added target.
  - Done when: `python3 tools/l3check.py --build-corpus` lists `point_walk_us2011` as runnable with its verdict (or, on a forged wrong-build corpus, as `FAIL (unmapped …)`), `runner.py run point_walk_us2011` returns the walker's verdict on the US page, `l3check --selftest` passes, and M9.10's Status/Result cites the row or states the name half as the only open half (the `poi_record_decode` runner plus M3.11b's text byte order; the accessor itself already runs, C-5110–C-5112).
  - Stop: if `runner.py` cannot host the walker without a sec1/INIT dependency it cannot satisfy (M1.2f), record the fault, keep the target BLOCKED-with-reason, and re-open M9.41 as `blocked` naming the dependency.
  - Falsifier: the row is runnable but returns a verdict on a wrong build (it must be `FAIL (unmapped …)`), or the walker verdict disagrees with `point_walk_l3.py walk` on the same page.
  - Claims: C-5770–C-5779
  - Result: `done` — EXP-2026-11-20-M9.55-us-poi-runner (C-5770–C-5779). `python3 tools/l3check.py --build-corpus` lists `point_walk_us2011` `PASS`/`ACCEPT` (`pass=2 fail=0 skip=0 blocked=7 runnable=2/9`, corpus 110 entries, exit 0); `runner.py run point_walk_us2011` on `archive/us256.img` gives `status PASS exit 0 verdict ACCEPT records 1000` (9/9 records identical to `point_walk_l3.py walk`); wrong build → `FAIL (unmapped 0x00000000 @ build us2011, UNMAPPED)` exit 5, bad offset → `INVALID`, forged `build` → `FAIL` from `build_targets.py` (`0 only-in-* across 8 copies`); `l3check --selftest` `OK (21 checks, 1 skipped)`, `runner.py --selftest` `OK (30 checks, 2 skipped)`. M9.10 keeps its walk half as S1 evidence, name half open on its own `poi_record_decode` runner (M3.11b closed, C-5810–C-5816). M9.41 re-opened and set `done` by rule 15.

- [x] **M9.57 — Find who subscribes the data-access task to object-store event 11 (state 3 of the mount)**
  - Status: done · Owner: task/m9.57-event11-subscriber · Critical: no
  - Step: P1
  - Depends: M9.52 (done)
  - Goal: M9.52 showed the mount reaches state 3 only through `0x003f6b1c`, the handler of object-store event `0x07d0` sub 11 with `+28 = 16` (C-5904), and `datask_l3.py --event 11:16` delivers that event as a stand-in. Find the real subscription (subscriber task `*0x011fff58`, event id 11), the object it watches and what makes the event carry 16, so the stand-in can be replaced by the object call that fires it.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --sdl --event 11:16` ends with `state 3`; `python3 tools/sh4xref.py archive/head256.img Navi.exe --image-start 0x200200 --to 0x003d18b0` lists the 92 `OBJ_Event_setPrm` sites M9.52 read (none names sub 11 for the data-access task, C-5907).
  - Scope: EU2011. (1) `Navi.exe` subscriptions with a non-literal event id (the 37 `OBJ_Event_setPrm` sites whose `r6` is not a `mov #imm`), and subscriptions made with `OBJ_Event_setPrmForMP` or a hand-filled block; (2) the other modules that import `OBJ_Event_setPrm` and could name the map task (`taskLibGetIDfromName("HDL_MapMainTask")`, the UTF-16 name is in `OSMDLL.dll`); (3) in `OBJDLL.dll`, which object's notifier puts 16 in the event's last word.
  - Done when: the EXP names the subscribing call (module, VA, object call) and the value 16's source, and `datask_l3.py` fires the event from a model of that object instead of `--event`; or the search is counted and negative with a positive control (the sub-100 subscription at `0x003eb99c` must be found by the same method).
  - Stop: if the subscriber is outside `Navi.exe` and needs that module's own task to run, name the module and export and stop.
  - Claims: C-6000–C-6009
  - Result: `docs/experiments/EXP-2026-11-20-M9.57-event11-subscriber.md` (C-6000–C-6006), by the counted-negative branch. New `tools/event_subs.py` lists every `OBJ_Event_setPrm`/`OBJ_Event_setPrmForMP` call of a segment from each module's own import table: EU2011 build A, 149 modules, 10 importers, 131 call sites, sub literal in every row. **Nobody subscribes the data-access task to sub 11**; the same census finds its subscriptions to 100, 199, 13, 6 and 1 (positive controls), and of the six rows of its event table 11 and 12 have no subscriber (12 is a bare `rts`). No function that addresses the task builds `0x07d0` by hand. State 3 therefore has no static sender in this firmware; `--event 11:16` stays a test switch, and the mount model needs no event 11 (M9.53: the map is served in state 2). No follow-up task.
  - Note (M9.53, C-5913): state 3 *refuses* map requests; requests are served in state 2. This task explains state 3 but is no longer on the path to road records.

- [x] **M9.59 — `l3_precond`: classify a target against its own build, and know targets that run outside `runner.py`**
  - Status: done · Owner: task/m9.59-l3-precond-classify · Critical: no · Pair: solo
  - Step: tooling
  - Depends: H45 (done)
  - Goal: M9.33 found two gate gaps (EXP-2026-11-20-M9.33-rerun-prereqs-map, C-3401/C-3402). (1) `--all-targets --image archive/head256.img` classes the US2011 VAs of `cmp_ind_reader_us2011` against EU sections (`INIT` instead of `CODE sec0`). (2) `tile_reader`, `drstr_parser` and `mmain_reader` are `BLOCKED` ("entry kind blocked with no VA") although their `reason` names the tool that runs them (`datask_l3.py`, `vcard_l3.py`, `mmain_l3.py`). The gate should say what is true.
  - Precheck: `python3 tools/l3_precond.py --selftest` passes; `python3 tools/l3_precond.py --target cmp_ind_reader_us2011 --image archive/head256.img` prints `va_class.0x00565d94: INIT` (the defect).
  - Scope: `tools/l3_precond.py` only. (1) Read the target's `build`: refuse a head whose SHA-256 is not that build's (or take `--image-us`), never class across builds. (2) A `blocked` entry whose `reason` names an existing `tools/*_l3.py`/`*.py` runner gets the verdict `RUNS-ELSEWHERE` (with the tool name), not `BLOCKED`. No `targets.json` change.
  - Done when: the two cases above print the corrected classes/verdicts on the real heads; a selftest case for each, plus a negative (a `blocked` reason naming a missing tool stays `BLOCKED`); `python3 tools/gate.py` green.
  - Stop: if a `RUNS-ELSEWHERE` state breaks `l3check`/`gate` consumers of the verdict enum, keep `BLOCKED` with a `runs_via` field instead and record why.
  - Claims: C-6060–C-6069
  - Result: EXP-2026-11-21-M9.59-precond-build-runs-elsewhere; C-6060–C-6069; selftest 45 PASS; --all-targets 7 READY/2 BLOCKED/4 RUNS-ELSEWHERE; gate 4 pass/0 fail/0 skip
