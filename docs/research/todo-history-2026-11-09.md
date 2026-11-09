# TODO history — 2026-11-09 (PO grooming archive)

Done tasks moved from `TODO.md` on 2026-11-09: completed (`Status: done`), block no open/in-progress/blocked task, and not completed on 2026-11-09 (conservative >24h proxy; commit dates on `origin/main` are the authority). See `todo-history-2026-11-05.md`/`2026-11-06.md` for earlier archives.

## H (archived)

- [x] **H1 — Repair the claim ledger and the EXP index**
  - Status: done · Owner: task/h1-claim-ledger · Critical: no
  - Depends: —
  - Goal: one ID per claim and every proposed claim registered.
  - Input: `docs/research/claims.md` (duplicate IDs C-070, C-110, C-543,
    C-546, C-558); claims proposed in EXP-38 (C-532/C-533), EXP-41
    (C-528…C-531), EXP-42 (C-520/C-521), EXP-43, EXP-44, EXP-46, EXP-47,
    EXP-48 that collide with existing rows or were never added;
    `docs/experiments/README.md` index (two EXP-29 and two EXP-35 files).
    Also unregistered (2026-11-06): the blocks of M2.1 (C-720…), M4.1
    (C-890…), M4.2 (C-900…), M4.5 (C-930…), M4.13 (C-1010…) and M5.8
    (C-1100…) have no rows; their EXPs state the findings. The ten missing
    `EXP-…-M*` index rows were added by H5.
  - Done when: a new `tools/claims_check.py` (in `tools/selftest.py`) reports
    zero duplicate IDs and every "proposed claim" in an EXP either has a row
    (new ID from this block, with `Was proposed as C-xxx in EXP-…`) or a
    one-line reason it was dropped; the EXP index lists the duplicate-number
    files with distinct labels. No EXP file is renamed (append-only).
  - Claims: C-600–C-609
  Result: root label slot copied verbatim, source order kept, `--label`
  override reported (EXP-2026-11-06-M5.12b-root-label, C-2030–C-2033).
  - Result: tools/claims_check.py (selftest green) reports 0 duplicate IDs and 0 unregistered proposed claims; ledger annotated; EXP index relabeled.

- [x] **H2 — Refresh AGENTS.md and research docs after EXP-35…51**
  - Status: done · Owner: task/h2-docs-refresh · Critical: no
  - Depends: —
  - Goal: no guide still sends agents down a retired lead.
  - Input: `AGENTS.md` "Firmware" section (still starts from
    `ce_rom_parse.py`, still describes the BT_MGR chain `0x6fab2c` →
    `0x6faeb0` → `0x6fb05c` with "data delta `0x02800000`" as the map-code
    check, still points to "TODO Step 2"); `docs/research/l3-ghidra.md`
    status table ("Reader entry points: only the map-code comparator chain");
    `docs/research/feedback-loop.md` L5 verdict (superseded by EXP-37);
    `docs/format/cerom.md` §5/§11 (`e32`/`o32` still `HYPOTHESIS`, now
    verified by EXP-35/-36/-48); `docs/research/roadmap.md`; links to old
    TODO sections (`Step 1b`, `Step 2`, `Gate 0a`, `P3`, `P7`) anywhere in
    `docs/` (`grep -rn "TODO Step\|TODO.md Step\|Gate 0a" docs`).
  - Done when: `grep -n "0x6faeb0\|0x02800000"` in these files only hits
    dead-end lists that name C-520/C-528; the first firmware command in
    AGENTS.md is `cerom.py`; the L5 verdict carries `Superseded by
    EXP-2026-11-05-37`; claims updated in the same commit.
  - Claims: C-610–C-619
  - Result: docs refresh across AGENTS.md, cerom.md, l3-ghidra.md, feedback-loop.md, roadmap.md, open-questions.md, claims.md (C-610–C-619); no EXP (docs-only)

- [x] **H3 — One CE ROM tool: fold `ce_rom_parse.py` into `cerom.py`**
  - Status: done · Owner: task/h3-ce-rom-tool · Critical: no
  - Depends: —
  - Goal: one parser for the CE ROM, so fixes land once.
  - Input: `tools/ce_rom_parse.py` (full-image `ECEC` scan + JSON report),
    `tools/cerom.py`, `tools/l3_harness/rommap.py` (docstring says it reads
    `ce_rom_parse.py` JSON).
  - Done when: `cerom.py scan IMG` lists every `ECEC` segment as the old tool
    did (same counts on `IMG256`: A 149 modules, B, C, copies);
    `ce_rom_parse.py` becomes a thin wrapper or prints a deprecation pointer;
    `rommap.py` docs name `cerom.py memmap`; both self-tests pass.
  - Claims: C-620–C-629
  - Result: tools/cerom.py scan + wrapper + rommap docs (EXP-2026-11-06-H3); selftest OK

- [x] **H4 — Audit the delta-era firmware claims**
  - Status: done · Owner: task/h4-audit-delta-claims · Critical: no
  - Result: docs/experiments/EXP-2026-11-06-H4-audit-delta-claims.md; claims C-630–C-639; candidate rows re-verified or retracted
  - Depends: —
  - Goal: every firmware claim from EXP-05…29 is either re-verified through
    `cerom.py` or retracted.
  - Input: `docs/research/claims.md` C-0xx…C-3xx firmware rows (candidates:
    C-068, C-180, C-182, C-234, C-262, C-370…C-375, the `0x1952b00` copy-list
    claims), EXP-13…29, `docs/format/firmware.md`; `cerom.py file2va`.
  - Done when: each candidate row has a new status (`RETRACTED` with
    `Superseded by`, or `VERIFIED` with the `cerom.py` module/section/offset);
    one EXP lists every row checked and the command used.
  - Claims: C-630–C-639

- [x] **H5 — Board review 2026-11-06 and real-image checks**
  - Status: done · Owner: claude/project-thread-euxe0q · Critical: no
  - Depends: —
  - Goal: check merged work against `IMG256` and update the board.
  - Done when: every "synthetic only"/"blocked" result since PR #11 is rerun
    on `IMG256` or its blocker re-checked; new tasks added.
  - Result: EXP-2026-11-06-H5-pm-review (C-1710–C-1716): M2.1 unblocked,
    `thunks` 0 % on real data, comphdr 187/245, M1.2b probe negative except
    xpress-lz77, OSM hosts 403.
  - Claims: C-1710–C-1719

- [x] **H6 — Reconcile `drstr.md` with the `MMAIN001` layout; document `tools_ze0`**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: —
  - Goal: no format doc contradicts a verified result.
  - Input: EXP-2026-11-05-M4.5 (`0x18c`/`0x1ac` fall inside FAT directory
    records `ER_INFO`); `docs/format/drstr.md` (per-language list at `0x18c`,
    3-section descriptor at `0x1ac`) and the claims behind it;
    `tools/ze0-viewer/tools_ze0/PROVENANCE.md` vs `setup.sh` and the
    `AGENTS.md` sentence "`tools/ze0-viewer/` clones a pinned `osm2clarion`".
  - Done when: the `drstr.md` claim is retracted or re-scoped to the file it
    really describes (new claim with `Supersedes`); `AGENTS.md` and
    `tools/README.md` say which copy of `tools_ze0` the harness uses and how
    the two are kept in step.
  - Result: `drstr.md` reconciled (MMAIN001 is the 4 KiB file; M4.5 read the FAT root dir) and `ze0-tools.md` added (EXP-2026-11-06-H6-drstr-docs).
  - Claims: C-1720–C-1729

- [x] **H7 — `tools/realcheck.py`: real-image regression run**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: a tool that passes its self-test but fails on real bytes is caught
    the same day (C-1714).
  - Input: EXP-2026-11-06-H5 commands and counts; `IMG256`.
  - Done when: `python3 tools/realcheck.py IMG256` runs `romhdr` (A: 149
    modules), `exports coredll.dll` on B (1651 names, ordinal 719 =
    `sprintf`), `imports Navi.exe` (846), `comphdr --all` (187/58), `thunks
    Navi.exe` (expected count, currently 0 → reported as FAIL), the
    `sh4xref.py` EXP-50 call sites, and `probe` on the two `NaviMapCC.dll`
    sections; each check prints PASS/FAIL against a pinned value and the
    script exits non-zero on any FAIL; `IMG256` SHA-256 is checked first;
    `tools/README.md` and rule 11 point to it. No vendor bytes in the repo.
  - Result: `tools/realcheck.py` runs eight pinned checks with SKIP/exit-2 without the image (EXP-2026-11-06-H7-realcheck).
  - Claims: C-1730–C-1739

- [x] **H8 — Fix what H6 reported: `mmain.py`, `setup.sh`, two doc sentences**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: — (coordinate with PR #35 `[M3.8]`, which reads `MMAIN001`)
  - Goal: no tool or guide still describes `MMAIN001.DAT` as a FAT log or
    `tools_ze0` as a network clone.
  - Input: EXP-2026-11-06-H6 "Not edited, reported" and follow-ups;
    `tools/mmain.py`; `tools/ze0-viewer/setup.sh` and `PROVENANCE.md`;
    `AGENTS.md` and `tools/README.md` sentences on `setup.sh`.
  - Done when: the root-directory parser is renamed for what it reads and a
    `MMAIN001.DAT` header parser round-trips the real file (self-test
    synthetic); `setup.sh` applies the patch to `tools_ze0/` paths and is
    run once in the EXP; the two sentences match `docs/format/ze0-tools.md`;
    `realcheck.py` pins the `coredll.dll` ordinals of C-1710 (H7 follow-up).
  - Result: `mmain.py` parses the real 4 KiB header and refuses root dirs; setup.sh
    audits/regenerates `tools_ze0`; docs and realcheck ordinal pins fixed
    (EXP-2026-11-06-H8-mmain-fix).
  - Claims: C-1890–C-1899

- [x] **H9 — Guard recompression tools against zlib-ng false failures**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: —
  - Goal: a correct rebuild must not report `FAIL` because the interpreter
    links zlib-ng (Python 3.14 here), and a user must learn why.
  - Input: `tools/lev3456.py verify/rebuild`, `tools/cmpind_writer.py`,
    `tools/ind_mutate.py`, `tools/cmpind.py`; the 2026-11-06 observation that
    `python3` 3.14 (`zlib 1.3.1.zlib-ng`) reports `stream differs … plain
    True` on `LEV3456R.DAT` while `python3.13` (stock `1.3.1`) returns
    byte-identical, matching `docs/format/cmp-ind.md` and `AGENTS.md`.
  - Done when: every tool that recompresses prints the zlib runtime version
    and warns (or refuses `verify`/`rebuild` when a byte-identical result is
    claimed) on `zlib-ng`, without changing synthetic `--selftest` results;
    one EXP records the 3.13-vs-3.14 run on the same `LEV3456R.DAT` SHA-256
    and the exit codes; `tools/README.md` states the requirement.
  - Result: `tools/zlibinfo.py` (stock/zlib-ng/unknown, exit 3 = unverifiable)
    wired into lev3456/cmpind_writer/cmpind/ind_mutate (EXP-2026-11-06-H9-zlib-ng-guard).
  - Claims: C-1970–C-1979

- [x] **H10 — PM review, fourth pass (2026-11-06)**
  - Status: done · Owner: claude/project-thread-wne7u7 · Critical: no
  - Depends: —
  - Goal: check what landed since the third pass on the real files and
    re-plan the board.
  - Done when: priorities and workstreams reflect the merged results, stale
    review text is moved to a history file, and every follow-up has a task.
  - Result: EXP-2026-11-06-H10-pm-review; old review sections in
    `docs/research/todo-history-2026-11-06.md`; new tasks M1.2e, M2.15, M2.16,
    M3.2b, M4.20, M5.12b, M5.12c, M5.13, M5.14; M5.4 reopened, M9.6
    re-scoped, M6.2/M6.5–M6.7 rewritten as S0–S3 for Marek.
  - Claims: C-2110–C-2119

- [x] **H12 — PM review, fifth pass (2026-11-06)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: check the ten tasks merged since the fourth pass against the real
    files and re-plan the board.
  - Done when: every merged task's `Result` matches its EXP, the follow-up
    lists of all 149 records are mined for uncovered work, and each new item
    has a task or a row in the retired-leads list.
  - Result: EXP-2026-11-06-H12-pm-review. Four claim blocks re-issued
    (C-2300…C-2349); H11's gaps G1–G8 became M9.17, M3.18, M4.21, M5.16–M5.19
    and M9.18; the follow-up sweep added M5.13b, M1.2f, M1.10, M1.11, M4.22,
    M5.1c, M5.20, M9.20, H13 and H14; the M5.8/M4.8c field mix-up is repaired.
  - Claims: none (a review creates no format claim)

- [x] **H13 — Doc debt: `tools/README.md` rows for `imgpatch`/`qemu-ze0`; refresh `roadmap.md`**
  - Status: done · Owner: claude/project-thread-9ynrai · Critical: no
  - Depends: —
  - Goal: a new agent must find every tool in `tools/README.md`, and
    `roadmap.md` must stop calling full-system QEMU out of scope while M8 is an
    active workstream.
  - Input: `tools/README.md` (no `imgpatch` row, no `qemu-ze0` row — checked
    2026-11-06); `docs/research/roadmap.md` ("Last updated 2026-11-05",
    "What not to do yet → Full-system QEMU", Gate 0 rows that predate
    M3.1–M3.10); `docs/research/full-system-emulation.md`.
  - Done when: `grep -n "imgpatch\|qemu-ze0" tools/README.md` finds both,
    `roadmap.md` names the current stage model (M1–M9 plus H11) instead of the
    retired gate text, and no row of it contradicts `TODO.md` or
    `reader-coverage.md`.
  - Result: `tools/README.md` has `imgpatch.py` and `qemu-ze0/` rows (their
    `--selftest` / `--help` pass); `roadmap.md` has a current stage model
    (M1–M9, H11, M8 F0–F5) and marks the 2026-11-05 gates as history
    (`selftest.py`: passed=29 failed=0 skipped=20; `claims_check.py`: OK).
  - Claims: none

- [x] **H14 — Verification debt: the checks the EXPs promised but never ran**
  - Status: done · Owner: claude/h14-verification-debt · Critical: no
  - Note: four of five tiles and `LEV3456R` reproduce; **`B30R048R` does not**
    (the harness's background rebuild raises on an opaque record), so its
    byte-identical pin is untrusted until M9.22 explains it.
  - Depends: —
  - Goal: five follow-ups ask for the same thing — run the pinned checks on
    the real samples once, so the `realcheck`/`harness` pins mean something.
  - Input: `cd tools/ze0-viewer && python3 harness.py verify` on the five
    pinned tiles (`B28R070R`, `B30R060R`, `B58R070R`, `B30R048R`, `LEV3456R` —
    EXP-2026-11-06-H8 follow-up); `tools/realcheck.py IMG256` with the extra
    `coredll.dll` ordinals 59/65/66/496/1047 (EXP-H7); `lev3456.py
    verify`/`rebuild --level 5` on the 2011 file (EXP-H9); `bash
    tools/qemu-ze0/build.sh --selftest` and `python3
    tools/qemu-ze0/gdb-ze0.py --selftest` in `tools/selftest.py` (EXP-M8.A7);
    `tools/l3_harness/ghidra_import.py --selftest` in the L3 selftest.
  - Done when: each command has a recorded result with the sample SHA-256,
    `tools/selftest.py` covers the qemu-ze0 scripts (SKIP when absent, never a
    silent pass), and a new pin is added only where the measured value is
    stable.
  - Claims: none
  - Result: EXP-2026-11-08-H14-verification-debt. selftest 47/0; realcheck 8 PASS; harness verify OK on B28R070R, B30R060R, B58R070R; **B30R048R fails** (`AssertionError((6, 29))`, negative, follow-up needed); lev3456 verify OK on stock zlib 1.3.2; build.sh selftest 42/0 with make, meson, ninja, gcc.

- [x] **H15 — PM review, sixth pass (2026-11-06)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: audit the three results merged after the fifth pass and re-sequence
    the board around what they proved.
  - Done when: the two scoped negatives change the priority order, every
    follow-up they create has a task, and the rule that would have prevented
    them exists.
  - Result: EXP-2026-11-06-H15-pm-review. Compression (M1.2f/M8.E1) is now the
    single gate for the software side; M9.11 re-scoped to the located chunk
    decoder `0x41c7e8` and runnable now; M9.10 and M3.11 marked blocked;
    M2.4's invalid "unavailable offline" blocker removed; M5.12c narrowed by
    M3.12; rule 14 added; H16 added.
  - Claims: none (a review creates no format claim)

- [x] **H16 — `tools/fetch_image.py`: pinned downloads so "no image" stops being a blocker**
  - Status: done · Owner: claude/h16-fetch-image · Critical: yes
  - Depends: —
  - Goal: four records (M5.13, M5.12b, M8.A4, M8.A5) list "no vendor image on
    this machine" in their scope although the host is reachable and rule 11
    forbids that blocker. One helper with pinned URLs, sizes and SHA-256
    removes the excuse and the transcription risk.
  - Input: `https://files.viaaq.eu/sd-images/` (listed 2026-11-06):
    `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (7.5 G, sha256
    `105e2032…76307`), `LEAF_2011-2012_US.img` (7.5 G, sha256 `53342430…c5383`),
    `LEAF_2014_EU_QSD-357-101.img` (7.4 G), `ENV200_2016_EU_QSD-390-100.img`
    (7.4 G); the existing `curl -r 0-268435455` recipe for `IMG256` (sha256
    `92aa525d…`); `docs/research/image-versions.md`.
  - Done when: `tools/fetch_image.py --list` prints the four images with size
    and SHA-256; `--image IMG256|US|EU2011|EU2014|EU2016 [--part 256M] -o PATH`
    downloads (resumable), verifies size and SHA-256 and leaves no partial
    file on failure; `--verify PATH` checks an existing file; `--selftest`
    covers the refusal paths against a local `file://` fixture (no network in
    tests); `tools/README.md`, rule 11 and the Shared-inputs table point to it
    and gain the two newer images.
  - Result: EXP-2026-11-08-H16-fetch-image. `tools/fetch_image.py` (`--list`, `--image`,
    `--verify`, `--selftest`); real IMG256 download verifies against `92aa525d…`.
  - Claims: none

- [x] **H17 — PM review, seventh pass: the tickets were under-specified (2026-11-06)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: three sessions in a row (M3.11, M3.2b, M3.13) produced "not found in
    the uncompressed sections". Marek's diagnosis: unclear task definition, not
    agent methodology. Make the template carry the feasibility test.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 memmap
    --json`, then sum compressed versus uncompressed section bytes per module
    (done: 56.2 % / `Navi.exe` 75.1 %).
  - Done when: `Precheck`, `Scope` and `Stop` are mandatory fields in the task
    template, rule 14 is a definition-of-ready rule, and every open reader task
    (M3.14–M3.16, M3.18) carries them.
  - Result: EXP-2026-11-06-H17-task-definition. Template extended, rule 14
    rewritten, four open reader tasks retrofitted, M1.12 added (the one-command
    precheck), reader-coverage gains the measured compression budget.
  - Claims: none (a review creates no format claim)

- [x] **H18 — PM review, eighth pass: method audit of the last 24 h (2026-11-06)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: the board now demands a precheck; the records must be checkable too.
    Audit every record dated 2026-11-06 for sample+hash, runnable commands,
    controls, scope and falsifier, and fix the template where they were never
    asked for.
  - Precheck: `ls docs/experiments/EXP-2026-11-06-*.md | wc -l` → 89 records;
    the audit script is in the EXP.
  - Scope: all 89 records dated 2026-11-06; no vendor bytes read.
  - Done when: the audit table is in an EXP and every gap is either fixed in
    `TEMPLATE.md`/rule 16 or has a task.
  - Result: EXP-2026-11-06-H18-method-audit. 8 records with no command block,
    8 with no sample hash, 39 that never mention a control, 1 with `# ...`;
    the load-bearing gaps are now M3.19 (committed SH-4 scanner) and H19
    (re-verify the five thinnest records). `TEMPLATE.md` gained the five-part
    Method, `Tools`, `Falsifier` and a `Reproduction` block.
  - Claims: none (a review creates no format claim)

- [x] **H20 — PM review, ninth pass (2026-11-08)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: sixteen results landed in two days; audit them, correct the
    compression premise, and re-sequence around what they proved.
  - Precheck: `git log --oneline 476dfb0..origin/main` (23 commits) and the 15
    new EXP records; `python3 tools/selftest.py`.
  - Scope: the records merged after the eighth pass; no vendor data read.
  - Done when: every result's `Done when` state is on the board, the wrong
    premise is retracted in the rule and in `AGENTS.md`, and every uncovered
    follow-up has a task.
  - Result: EXP-2026-11-08-H20-pm-review. Compression premise retracted
    (0 compressed executable sections); M3.2b/M3.13 re-opened, M3.14–M3.16/
    M3.18 prechecks corrected; M9.20 promoted (blocks M9.14/M9.17); new
    M1.14, M1.10b, M2.17, M4.23, M9.22, H21; M5.12c marked in progress;
    M1.13/M5.21 dangling EXP/claim references fixed.
  - Claims: none (a review creates no format claim)

- [x] **H21 — Image pin audit: hash the archive images, pin 2016**
  - Status: done · Owner: task/h21-image-pin-audit · Critical: no
  - Depends: — (H16 done)
  - Goal: `tools/fetch_image.py` pins four images, but the two 2014/2016 rows
    have no verified SHA-256 (only the 2011 EU/US do), and the copies already
    in `archive/sd-images/` were never hashed against the pins.
  - Precheck: `python3 tools/fetch_image.py --list` and `ls -l
    archive/sd-images/`.
  - Scope: hashing only; no image is downloaded by the test.
  - Done when: each local image's SHA-256 is recorded in
    `docs/research/image-versions.md`, the two missing pins are added to
    `fetch_image.py` (from a real download, size + hash), and a mismatch
    between a local copy and a pin is reported as a finding, not silently
    accepted.
  - Stop: if an image is absent locally and the download is not allowed in the
    session, record the gap and stop.
  - Claims: none
  - Result: EXP-2026-11-08-H21-image-pin-audit. All 4 local `archive/sd-images/`
    images hashed and matched recorded pins (0 mismatches); EU2016 full-image
    SHA-256 pinned in `fetch_image.py` (EU2014 was already pinned; both verified);
    shared-input rows and `image-versions.md` updated. (Recovered/re-merged after
    coordinator merge error.)

- [x] **H22 — PM review, tenth pass (2026-11-08)**
  - Status: done · Owner: session-PM · Critical: no
  - Depends: —
  - Goal: audit the 15 results merged after the ninth pass, correct stale
    board state, and file follow-ups from experiment records.
  - Precheck: `git log --oneline 476dfb0..origin/main` (23 commits) and the new
    EXP records; `python3 tools/selftest.py`; `python3 tools/claims_check.py`.
  - Scope: TODO/reader-coverage consistency and follow-up mining; no vendor
    data read.
  - Done when: completed/blocked task states match their EXPs, priorities and
    the workstreams table reflect reality, M1.13's result is reflected in
    M5.21, M9.21's misplaced result is moved to its own task block, and every
    uncovered follow-up has a task.
  - Result: EXP (this pass, board-only). M1.13 done (471/471 factory pages,
    stock zlib L6/m8) — the 0.8 % premise retracted and M5.21 re-scoped to slot
    budget. M9.14/M9.17 re-blocked on compressed sec1 `.data` (M1.2f + M9.24 /
    M1.2f). M9.11 firmware path PASS, registration blocked on M9.11b. M9.22
    done (B30R048R explained). M5.4 done (real tile, structural L2). M3.14/15,
    M4.16b, M4.22, M5.12c correctly blocked. New tasks: M4.24, M4.25, M4.26,
    M5.22, M5.23, M5.24, M9.25.
  - Claims: none (a review creates no format claim)

- [x] **H23 — Board hygiene: claim-block collisions, duplicate M9.21, stale status lines**
  - Status: done · Owner: PM/review (session) · Critical: yes
  - Depends: —
  - Goal: make TODO.md safe for ~15 parallel agents again. The 11th-pass audit
    found: duplicate M9.21 task blocks (both done); M4.24 claims `C-2630–C-2639`
    colliding with M9.22/M9.23, M4.25 `C-2640–C-2649` colliding with M9.24,
    M4.26/M1.15/M5.22/M5.23 colliding on `C-2650–C-2659`; M5.25 colliding with
    H25 on `C-2750–C-2759`; H26–H29 colliding with M9.26/M4.30/M4.24/M4.25 on
    `C-2760–C-2799`; M3.20/M5.23/M5.24 had incomplete claim fields; M9.23 had a
    stale "next free block" note; workstreams table said "M3.19 done" while
    M3.19 is `blocked` (EXP-2026-11-08-M3.19-sh4scan, unblock M3.20).
  - Precheck: `grep -n 'Claims: C-2630\|Claims: C-2640\|Claims: C-2650\|Claims: C-2750\|Claims: C-2760\|Claims: C-2770\|Claims: C-2780\|Claims: C-2790' TODO.md`
    and `grep -n '^\- \[.\] \*\*M9\.21' TODO.md` reproduced the collisions/dup.
  - Scope: `TODO.md` only. Reassigned colliding claim blocks to free blocks
    (recorded as `Claims: C-xxxx–C-yyyy (was ..., collision fixed by H23)`),
    kept M9.22 `C-2630–C-2639` (registered in `claims.md`) and M9.24
    `C-2640–C-2649`; merged duplicate M9.21; added/fixed claims for M5.24/M9.23;
    fixed M9.22 formatting and M3 workstream status. Did not change task
    meaning, owners, or results.
  - Done when: no `Claims:` range appears in more than one task block (verified
    by script, recorded in commits), only one M9.21 block remains, M3.20/M5.23/
    M5.24 have claim blocks, and the M3 workstream row matches actual statuses.
  - Stop: if any reassigned block is already used in `docs/research/claims.md`,
    do not move it; record the conflict and take a different free block.
  - Claims: C-2710–C-2719
  - Result: board-only (no EXP). Commits `17eceaf` (partial) + this commit.
    Verification: duplicate claim ranges = 0; M9.21 blocks = 1; M3.20/M5.23/
    M5.24 have Claims; M3 workstream shows M3.19 blocked (→M3.20).
    `claims_check.py: OK`.

- [x] **H24 — `todo_check.py`: lint TODO syntax, claim allocations and task fields; make selftests tmp-safe**
  - Status: done · Owner: task/h24-todo-check · Critical: yes
  - Depends: H23
  - Goal: prevent rule 9 / claim-block collisions, malformed tasks and
    incomplete metadata from recurring, and stop environment fragility from
    masking real regressions. `claims_check.py` validates `claims.md` but not
    TODO structure/allocations; current `mkcard --selftest` fails in
    constrained `/tmp` (`Disk quota exceeded` during reconcile synthetic-image
    copy on this machine, Python 3.14 `copy_file_range`), so `selftest.py`
    reports 1 FAIL on an otherwise clean tree.
  - Precheck: `python3 tools/claims_check.py` is OK while TODO has the H23
    collisions; `python3 tools/mkcard.py --selftest` exits 1 with the quota
    error under constrained `/tmp` (reproduced 2026-11-08).
  - Scope: new `tools/todo_check.py` (stdlib, with `--selftest`; one tool,
    name stated) + minimal fixes to selftests that create large temp images
    (`mkcard` and any other offender found by the same pattern) to honor
    `TMPDIR`/prefer `/tmp/opencode` and avoid unnecessary whole-image copies.
    Lint scope is `TODO.md` syntax/structure, not task semantics.
  - Done when: the lint parses every task block and reports: duplicate task IDs,
    duplicate TODO claim ranges, malformed/overlapping `Claims: C-xxxx–C-yyyy`,
    tasks missing required fields (`Status`/`Owner`/`Critical`/`Depends`/`Goal`/
    `Done when`/`Claims`), search/firmware tasks missing `Precheck`/`Scope`/
    `Stop`, `blocked` tasks missing `Unblock`, `done` tasks missing a `Result:`
    line, checkbox/status contradictions, invalid status/critical values, and
    `Depends` references to unknown IDs (warning or error, stated). `--selftest`
    covers a synthetic collision/malformed case; `mkcard --selftest` passes
    with `TMPDIR=/tmp/opencode` in a constrained environment (or skips the
    large-copy subcase with a clear reason, never a false FAIL); the tool is
    wired into `tools/selftest.py` discovery and documented in `tools/README.md`.
  - Stop: do not weaken existing selftest assertions to make the quota case pass;
    fix the temp/copy strategy instead. Do not turn semantic disagreements into
    lint errors without an explicit allowlist.
  - Claims: C-2720–C-2729
  - Result: EXP-2026-11-08-H24-todo-check.md; `tools/todo_check.py` (stdlib, `--selftest`/`--json`) lints TODO task IDs/claim ranges/required fields/status/blocked+Unblock/done+Result/checkbox contradictions/unknown Depends; `tools/mkcard.py` R5 reconcile selftest made tmp-safe (no whole-image copy); `tools/README.md` + `selftest.py` discovery wired; fixed minimal factual board defects (5 done-missing-Result, 3 claim overlaps M3.11c/M4.8d/M9.11b, M4.16 checkbox). `todo_check --selftest` OK, `todo_check TODO.md` OK, `mkcard --selftest` OK, `claims_check` OK.

- [x] **H26 — Pipeline L1/L2 na fixture’ach syntetycznych i generowanych (CI)**
  - Status: done · Owner: task/h26-ci-l1l2-fixtures · Critical: yes
  - Depends: H25
  - Goal: automatycznie mierzyć postęp warstwy „format/struktura akceptowalna offline”: potrafimy zbudować lub zmutować dane tak, że `cardcheck.py` (L1) i wybrane ścieżki `l2check.py`/round-trip przechodzą — bez twierdzenia, że firmware je zaakceptuje. To bezpośredni wskaźnik celu „generować obrazy kart SD”, ograniczony do tego, co da się udowodnić offline.
  - Precheck: `python3 tools/cardcheck.py --selftest`/help i `python3 tools/l2check.py --selftest`/help działają; istnieją narzędzia generujące fixture (`mkcard.py`, `imgpatch.py`, `cmpind_writer.py`, `drstr_ze0`/harness tam gdzie mają `--selftest`). Jeśli brak syntetycznego wejścia dla danej ścieżki L2, ścieżka jest raportowana jako `NOT COVERED`, nie jako PASS.
  - Scope: job/workflow (może rozszerzać H25, osobny plik lub wspólny) uruchamiający: (a) L1 na obrazie/drzewie wygenerowanym w teście z fixture syntetycznego (np. ścieżka `mkcard`/minimal tree — zgodnie z aktualnymi narzędziami; nie commitować vendor danych), (b) round-tripy L2 oparte o selftesty/narzędzia: `cmpind` preserved/recompress tam gdzie stock zlib dostępny, DRSTR rebuild, tile round-trip na syntetycznych/małych przypadkach obsługiwanych przez narzędzia, mutacja POI tam gdzie fixture jest syntetyczny. (c) Jawny raport: `L1 synthetic`, `L2 DRSTR`, `L2 cmp/ind`, `L2 tile`, `L2 POI mutation` — każdy PASS/FAIL/SKIP/NOT COVERED z komendą. **Poza zakresem:** golden EU2011 na prawdziwym `ROOT` (wymaga vendor tree), pełne 194 pary na prawdziwym REFER001, `--include-lev` na prawdziwym pliku.
  - Input: `tools/cardcheck.py`, `tools/l2check.py`, `tools/cmpind.py`, `tools/mkcard.py`, `tools/imgpatch.py`, `tools/selftest.py`; golden/profile tylko jeśli są w repo i nie zawierają danych vendorowych (`tools/golden/eu2011.json` to hashe/liczniki — użyć ostrożnie, bez wymagania obrazu).
  - Done when: CI produkuje artefakt JSON/Markdown z macierzą L1/L2 (per check) i exit code odzwierciedla tylko checks uznane za „runnable” w tej warstwie; dodanie nowego syntetycznego przypadku L1/L2 wymaga tylko dopisania do listy checks, nie zmiany logiki raportu. EXP opisuje pokrycie (co realnie mierzymy) i luki (co nadal wymaga vendor data / M5/M6).
  - Stop: nie symulować PASS przez pomijanie walidacji; jeśli L2 wymaga stock zlib 1.3.1 do byte-identical i runner ma zlib-ng, check jest `SKIP (zlib-ng, H9)` z linkiem do uzasadnienia. Po 2 nieudanych próbach ustabilizowania bez zmiany semantics — `blocked` + EXP.
  - Claims: C-2760–C-2769
  - Result: EXP-2026-11-08-H26-l1l2-fixtures.md (C-2760); `tools/l1l2_fixtures.py` (data-driven registry, `--selftest`/`--json`/`--md`) + `.github/workflows/l1l2-fixtures.yml` produce JSON/MD L1/L2 matrix (L1 synthetic, L2 DRSTR, L2 cmp/ind, L2 tile, L2 POI mutation) with runnable-only exit; local run 6P/0F/1S/2 NOT COVERED, verdict OK. No vendor data, no firmware acceptance claim (rule 13).

- [x] **H30 — Fix M9 rule-14 metadata and tighten `todo_check` firmware-task classification**
  - Status: done · Owner: task/h30-m9-rule14-metadata · Critical: no
  - Depends: H24
  - Goal: make rule 14 enforceable on the board. `todo_check.py` currently warns
    (not fails) on M9 firmware/search tasks missing `Precheck`/`Scope`/`Stop`
    and on M9.14 missing `Goal`; open/blocked M9.10, M9.11b, M9.12–M9.18 and
    M9.24 still violate the fields the rule requires, so the warnings are easy
    to ignore.
  - Precheck: `python3 tools/todo_check.py TODO.md` reproduces the M9 warnings;
    `python3 tools/todo_check.py --selftest` passes.
  - Scope: `TODO.md` metadata for the warned M9 tasks and `tools/todo_check.py`
    classification/severity behavior. No task semantics, no format claims, no
    status changes except where metadata is added to an existing state.
  - Input: `tools/todo_check.py`, rule 14 in `TODO.md`, current M9 task blocks
    (M9.10–M9.18, M9.20, M9.21, M9.24), H24 EXP.
  - Done when: each open/blocked warned M9 task has truthful `Precheck`,
    `Scope` and `Stop` fields (and M9.14 has `Goal`) consistent with its current
    blocker/result; `todo_check.py` documents which task shapes count as
    firmware/search and, for those shapes in open/blocked state, either fails
    or has an explicit `--strict`/configurable mode covered by selftest; done
    tasks are not made false-failing retroactively unless the change is trivial
    and correct.
  - Stop: if a task's real precheck/scope cannot be stated without re-doing the
    research, record that as a narrow follow-up task instead of inventing
    metadata.
  - Claims: C-2980–C-2989
  - Result: EXP-2026-11-08-H30-rule14-metadata.md. Added truthful rule-14
    `Precheck`/`Scope`/`Stop` to open/blocked M9.10, M9.11, M9.11b, M9.12–M9.18,
    M9.24 and `Goal` to M9.14; trivial/correct metadata to done M9.20/M9.21.
    `tools/todo_check.py` documents M1/M2/M3/M8/M9 as firmware/search and adds
    `--strict` (open/blocked/in-progress missing P/S/S error; done warns only),
    covered by selftest. Default `todo_check TODO.md` OK, `selftest --only
    todo_check` PASS, `claims_check` OK. No vendor data, no format claim.

## M (archived)

- [x] **M1.12 — `tools/reader_precheck.py`: can this reader be found statically?**
  - Status: done · Owner: claude/m1.12-reader-precheck · Critical: yes
  - Depends: —
  - Goal: make rule 14's `Precheck` one command instead of a session. The
    board now needs, per module: how much of it is compressed, which sections,
    and whether a given anchor (string literal, pool VA) has an xref in
    decodable bytes.
  - Precheck: the baseline below is already measured; if `cerom.py memmap
    --json` on `IMG256` does not reproduce it, stop and record the difference.
  - Scope: build A (B/C on request); static only; no vendor bytes committed.
  - Input: `cerom.py memmap --json` (per-section `compressed`, `vsize`,
    `file_offset`), `sh4xref.py` (literal-pool resolution); measured baseline
    for build A: 53,725,980 B of section vsize, 30,212,810 B compressed
    (56.2 %), 133/149 modules with a compressed section, `Navi.exe`
    16,778,254 B compressed (75.1 %, `sec1` 16.7 MB).
  - Done when: `python3 tools/reader_precheck.py IMG --image-start 0x200200
    --module Navi.exe [--anchor 0x00179364]` prints the module's compressed
    share and section list, says for each anchor whether it is referenced from
    decodable bytes, and exits non-zero when the anchor's only xref is inside a
    compressed section; `--table` prints the per-module table quoted in
    `docs/format/firmware.md`; `--selftest` pins the build-A counts above and
    covers both verdicts.
  - Stop: if the counts cannot be reproduced on `IMG256`, record the
    discrepancy and stop — do not re-derive the map by hand.
  - Result: EXP-2026-11-08-M1.12-reader-precheck. `tools/reader_precheck.py`
    reproduces the build-A baseline on `head256.img` (real pins in
    `--selftest`; `cerom.py memmap` agrees). It reports the census, the calls
    into compressed sections (direct, or indirect through a slot) and anchor
    verdicts. Its `Navi.exe` run shows the M3.15 call is an indirect call
    through compressed slot `0x0055d924`: C-2200, C-2201 and
    C-2202 are superseded in their call-target clauses (C-2513, C-2515; their
    rows are marked RETRACTED under M1.15, not here). The
    `sh4xref --calls` defect is M1.15. The done-when wording is operationalised
    as the EXP's Interpretation states.
  - Claims: C-2510–C-2519

- [x] **M1.3 — `cerom.py decompress` on all 245 sections**
  - Status: done · Owner: task/m1.3-decompress-all · Critical: yes
  - Result: EXP-2026-11-06-M1.3-decompress-all — 245 sections, 0 OK / 245 UNSUPPORTED / 0 FAIL; codec unidentified (M1.2c next).
  - Depends: M1.2b or M1.2c
  - Goal: complete RW data for every module.
  - Input: the decoder from M1.2b/c; `cerom.py extract`.
  - Tool: `cerom.py decompress` is implemented and self-tested (LZSS/LZX
    dispatch, per-section OK/UNSUPPORTED/FAIL, `--check`/`--out`/`--json`);
    only the real 245-section run is left (EXP-53, C-571).
  - Done when: `cerom.py extract --decompress` writes all 245 sections and
    every output length equals the header length (failures listed); IAT
    `FirstThunk` of `Navi.exe` (`0x0054d000` here; `imports` prints the first
    slot at `0x0055d000`, check which is right) decodes to slot values that
    `imports` predicts.
  - Claims: C-670–C-679

- [x] **M1.7 — Which kernel (B or C) boots with A**
  - Status: done · Owner: task/m1.7-kernel-select · Critical: no
  - Tool: `tools/kernel_select.py` scores B vs C on seven criteria and
    refuses a verdict on ties; fed the recorded B/C fields it returns
    `UNKNOWN` (EXP-54, C-572), so the decision still needs `ulRAMFree`/`End`
    or the `pExtensions` region from the image.
  - Depends: —
  - Goal: know which kernel and drivers the unit really runs.
  - Input: `ROMHDR` `ulRAM*`, `pExtensions` of B and C (`cerom.py romhdr`);
    `UpdateMng.exe` / `PRGUpdate.exe` strings and code in B; the 4-byte
    header difference between B and C; C-535 boot chain.
  - Done when: an EXP states B, C or "IPL-selected" with the evidence, and
    the boot-argument field that selects it if any (feeds M8.B4).
  - Claims: C-700–C-709
  - Result: EXP-2026-11-06-M1.7-kernel-select (verdict: IPL-selected; 12-byte boot arg is a Navi version string, not a selector)

- [x] **M1.8 — SH-4 disassembly and xref helper**
  - Status: done · Owner: claude/project-thread-wn7y0u · Critical: yes
  - Depends: —
  - Goal: one command answers "which code loads VA X" and "what does
    function Y call", the step every M2/M3 task needs.
  - Input: `cerom.py` (module sections at their VAs), `sh4-linux-gnu-objdump`,
    EXP-50 method (`mov.l @(disp,PC),Rn` = `0xDnnn`, literal at
    `(PC & ~3) + 4 + disp*4`; `jsr @Rn` = `0x4n0B`; `bsr`).
  - Done when: `tools/sh4xref.py IMG MODULE --to 0x004e7d28` lists every
    instruction that loads that literal with the enclosing function start
    (prologue heuristic) and `--calls FUNC` lists its call targets named via
    exports/thunks; it reproduces EXP-50's four call sites; self-test on
    synthetic SH-4 bytes.
  - Claims: C-710–C-719
  - Result: EXP-2026-11-05-M1.8-sh4xref (`tools/sh4xref.py`; 17 self-test checks; reproduces the four EXP-50 call sites; HDD_INFO slot 0x004e7d28 read at 0x004e7bec in fn 0x004e7b8c)

- [x] **M1.9 — Cross-image import names (A → B's `coredll.dll`)**
  - Status: done · Owner: task/m1.9-cross-image-imports · Critical: yes
  - Depends: —
  - Goal: every import of every A module named, not just numbered.
  - Input: `cerom.py --image-start 0x3e00200 IMG256 exports coredll.dll`
    (1651 names, C-527, C-1710); `imports` of A modules; other B/C
    exporters (`commondll.dll`, `SYS_INF.dll`, `Errlogdll`, `CEDDK.dll`).
  - Done when: `cerom.py imports MODULE --resolve-with 0x3e00200` (or a
    `--names FILE` JSON) prints `COREDLL!_wfopen` instead of `#1145` for all
    846 `Navi.exe` slots, unresolved ones listed; `sh4xref.py --calls` uses
    the names; synthetic self-test.
  - Result: `tools/cerom.py imports --resolve-with/--names` resolves ordinal
    imports via B/C exporter tables and lists unresolved slots;
    `tools/sh4xref.py --calls/--resolve-with/--names` uses resolved names.
    IMG256 (A `0x200200`, B `0x3e00200`, sha256 `92aa525d…`): Navi.exe 846
    slots, 697 resolved, 149 unresolved (no exporter in B, e.g. XGLDLL/OSMDLL);
    `COREDLL!_wfopen` at slot `0x0055d118` (1145). Synthetic self-tests in
    `cerom.py` (359 checks) and `sh4xref.py`; `tools/selftest.py` 30/0/19.
    EXP-2026-11-06-M1.9-cross-image-imports.md; claims C-1760–C-1769.
  - Claims: C-1760–C-1769

- [x] **M1.10 — Name the last 149 `Navi.exe` import slots**
  - Status: done · Owner: claude/m1.10-import-names · Critical: no
  - Depends: — (M1.9 done)
  - Goal: 149 of 846 slots stay `#NNN` because the exporter is not in build B
    (`XGLDLL`, `OSMDLL`). Unnamed slots weaken every Ghidra and L3 label.
  - Input: `cerom.py imports Navi.exe --resolve-with 0x3e00200` (unresolved
    list); `cerom.py exports` over the **image A** modules (the exporters may
    be A modules, not B) and over `commondll.dll`, `SYS_INF.dll`, `Errlogdll`,
    `CEDDK.dll`; `va2file` for the module base.
  - Done when: every slot is either named (`MODULE!export`) or listed as "no
    exporter in any image" with the search that showed it (positive control: a
    slot that already resolves); coverage is reported and the remaining names
    are in the EXP.
  - Result: `Navi.exe` 846/846 named once images A, B and C are all resolvers;
    the 149 gaps were `XGLDLL` (108) and `OSMDLL` (41), exporters in image A
    (EXP-2026-11-07-M1.10-import-names). Call-site check moved to M9 (C-2476).
  - Claims: C-2470–C-2479

- [x] **M1.11 — SH-4 decoder in `tools/`, with the LE convention pinned**
  - Status: done · Owner: claude/m1.11-sh4dis · Critical: no
  - Depends: —
  - Goal: four EXPs stopped at "needs SH-4 disassembly tooling"
    (M3.4, M3.9, M3.10, M8.E1b) and M8.E1 lost a whole round to a BE/LE
    confusion. One repo tool must decode the subset and state the endianness
    it assumes.
  - Input: `tools/sh4xref.py` (now decodes through `sh4dis.py`; before this
    task it shelled out to `sh4-linux-gnu-objdump`),
    EXP-2026-11-06-M8.E1b (LE halfwords; pattern `20e28553184229233823038b`
    at `0x88038666`), the 4-instruction import stub (M1.6b), `cerom.py sections`.
  - Done when: `tools/sh4dis.py` decodes the subset the reader work uses
    (`mov.l/mov.b/mov.w/add/sub/cmp/eq/tst/bf/bt/jsr/bsr/jmp/rts/nop/shl/and/
    or`) from LE halfwords, prints VA + mnemonic + resolved literal target,
    reproduces the `0x880385e4` prologue and the flag test at `0x88038666`,
    and `sh4xref.py` can use it when objdump is absent (same output on the
    pinned call sites); `--selftest` includes the BE trap case.
  - Result: `tools/sh4dis.py` (LE pinned in `read_u16`); `--check-real` reproduces the `nk.exe` prologue, flag test and four pools on IMG256; `sh4xref.py` output on the four M1.8 pinned sites byte-identical with no `PATH` binaries; sweep invariant 0 violations (EXP-2026-11-08-M1.11-sh4dis). Discrepancy: `sh4xref.py` never shelled out to objdump (C-2487).
  - Claims: C-2480–C-2489

- [x] **M1.14 — SH-4 decoder debt: one LE reader, a pinned `mov.w` and an oracle**
  - Status: done · Owner: task/m1.14-sh4dec-debt · Critical: no
  - Depends: — (M1.11 done)
  - Goal: M1.11 landed `tools/sh4dis.py`, but its follow-ups leave three
    holes: the LE halfword reader is now duplicated in `sh4scan.py`, one
    addressing mode is unverified, and nothing independent checks the decoder.
  - Precheck: `python3 tools/sh4dis.py IMG nk.exe --image-start 0x3e00200
    --check-real` and `tools/sh4scan.py --selftest` must both pass first.
  - Scope: `tools/sh4dis.py`, `tools/sh4scan.py`, `tools/sh4xref.py`; no
    firmware conclusions are re-derived.
  - Input: EXP-2026-11-08-M1.11-sh4dis (7 follow-ups: the duplicated
    `read_u16`, `mov.w @(disp,PC)` unpinned → C-2489 stays UNKNOWN, the
    missing independent oracle, the `vsize`-past loads, the display
    differences vs M1.8); `tools/point_walk_l3.py` (mask constants it uses).
  - Done when: one shared `read_u16`/`Mem` implementation is imported by both
    tools (no second copy), `mov.w @(disp,PC)` is pinned against one real
    decoded value on `IMG256` (C-2489 then VERIFIED or the pin recorded as a
    negative), and a second decoder (binutils `objdump` or a different
    implementation) agrees on the four M1.8 call sites.
  - Stop: if the oracle disagrees, record the disagreement per instruction and
    stop — do not adjust the tool until the oracle is explained.
  - Claims: C-2590–C-2599
  - Result: EXP-2026-11-08-M1.14-sh4dec-debt. `sh4scan.py` uses `sh4dis.halfwords_le` (shared LE reader, no duplicate). `mov.w @(disp,PC)` pinned synthetic + real (Navi.exe A `0x003f51a8/ae/c2`, pool `0x04e8/0x03ff/0x4e20`; C-2129 `fn 0x003f5194` uses it at 3 sites), resolving C-2489 for the mode; `0x88038666` still decodes the same. `--oracle` checks four M1.8 sites with Capstone/sh4*-objdump or pinned `SKIP` when absent (test host: SKIP). Selftests/claims_check green.

- [x] **M1.15 — `sh4xref.py --calls`: model the slot dereference**
  - Status: done · Owner: task/m1.15-sh4xref-slot · Critical: no
  - Depends: — (M1.8 and M1.12 done; the defect was found in M1.12)
  - Goal: `--calls` prints `jsr @r3 -> 0x0055d924` for `fn 0x004125a8`, but
    `0x0055d924` is a slot: the code runs `mov.l @(pc),r3; mov.l @r3,r3;
    jsr @r3` and calls the word stored there (C-2513, C-2514). Make the tool
    name the slot as an indirect call and never print a target it has not read.
  - Precheck: `python3 tools/reader_precheck.py --module Navi.exe --anchor
    0x004125a8` (M1.12) — the call at `0x004125de` is class `indirect`; the
    `sh4xref.py --calls 0x004125a8` output for `0x004125e2` must say the same.
  - Scope: build A; `tools/sh4xref.py` only (its `--selftest` gains the
    dereference form, and a direct `jsr` of the same shape stays direct).
  - Done when: `sh4xref.py IMG Navi.exe --calls 0x004125a8` labels `0x004125e2`
    as an indirect call through slot `0x0055d924` with no target, the
    `0x00412614` call to `0x0040b358` stays direct, `--selftest` covers both,
    and an EXP records the before/after output. Also: the rows C-2200, C-2201
    and C-2202 (M3.15's block) get Status `RETRACTED` and `Superseded by
    C-2513 / C-2515 / C-2514` in Evidence, as C-2513 to C-2515 record; this is
    the only change to another block's rows.
  - Stop: if the change alters another `--calls` line in build A beyond these
    sites, record the diff in an EXP and stop.
  - Result: `tools/sh4xref.py --calls` models `mov.l @Rm,Rn; jsr @Rn` as
    `indirect slot <va>` (no target); `fn 0x004125a8` `0x004125e2` →
    indirect slot `0x0055d924`, `0x00412614` stays direct `0x0040b358`;
    `--selftest` covers both. C-2200–C-2202 retracted (Superseded by
    C-2513/C-2515/C-2514). C-2850–C-2853.
    EXP-2026-11-08-M1.15-sh4xref-slot-deref.md.
  - Claims: C-2850–C-2859 (was C-2650–C-2659, collision with M4.26/M5.22/M5.23 fixed by H23)

- [x] **M1.17 — Verify factory zlib params across non-POINT generated file types**
  - Status: done · Owner: task/m1.17-zlib-params-nonpoint · Critical: no
  - Depends: M1.13
  - Goal: M1.13 reproduced 471/471 factory inner pages of `REFER001/POINT001–009`
    with stock zlib L6/memLevel 8. The compiler also writes/repacks `ADDRE*`,
    `ZCODE*`, `ICODE001`, `COORD001`, `LCTBL001`, `INTER*`/`FRWAY*` (if
    generated), `LEV3456R` and `MAPAL001` tile streams. A different producer
    per family would invalidate byte-identical/slot-budget assumptions.
  - Precheck: `python3 tools/factory_zlib.py --help` (or the M1.13 tool) works;
    at least one factory pair from each covered family is available in the
    extracted tree (`ROOT/REFER001`, `ROOT/MAPAL001`). If `ROOT` is absent,
    use `IMG256`/extracted files per rule 11, not a blocker claim.
  - Scope: sample real factory `.cmp/.ind` pairs for each family listed in
    `reader-coverage.md` rows that are compressed containers; compare factory
    inner streams to stock zlib candidates (reuse `factory_zlib.py`). Count
    reproduced vs not; do not test on synthetic data.
  - Done when: the EXP lists per family: sample SHA-256, page/stream count,
    best-matching params, reproduced count, and whether L6/m8 is sufficient;
    any family that does not reproduce is filed as a follow-up with the
    observed byte differences characterized (header, dynamic block, strategy),
    not guessed.
  - Stop: after one representative pair per family (more only when the first
    disagrees); do not brute-force every pair in the image.
  - Claims: C-2740–C-2749
  - Result: EXP-2026-11-08-M1.17-zlib-params-nonpoint. EU 2011 representative
    samples (stock zlib 1.3.2, H9 context): L6/m8/default/wbits15 sufficient for
    all losslessly-recovered streams across ADDRE/ZCODE/ICODE/COORD/INTER/FRWAY
    outer+inner, LCTBL001 embedded, MAPAL001 tile embedded, and LEV3456R L5
    strict + L3/L4 model-plain-matching decoded (21571 streams/pages reproduced,
    0 mismatches where plain recovered). LEV3456R L3/L4 model gaps/opaque
    records left as zlib-untested follow-up. (Recovered/re-merged after
    coordinator merge error.)

---

- [x] **M2.1 — `Navi.exe` function that opens `HDD_INFO.TXT`**
  - Status: done · Owner: task/m2.1-hddinfo-fn · Critical: yes
  - Depends: — (M1.8 helps)
  - Goal: name the function, its arguments and callers.
  - Input: literals at `Navi.exe` VA `0x004e7d28` / `0x004e7d2c` (C-521);
    `cerom.py --image-start 0x200200 IMG sections Navi.exe`; `imports`
    (CreateFile/ReadFile ordinals of `COREDLL`).
  - Done when: the EXP gives the function VA, the file API calls it makes,
    the buffer it fills (base register, offsets, lengths), and its callers
    (VA list).
  - Result: EXP-2026-11-06-M2.1-hddinfo-fn-complete (IMG256 `92aa525d…`): `fn 0x004e7b8c`
    (0x004e7b8c..0x004e7cfc) `HDD_INFO_read(r4 ignored,r5 selector,r6 out@r8)`,
    named calls `memset,_wfopen,fgetws,wcschr×2,wcsncpy,fclose,sub_004dd1f0`;
    line buffer `r15+0x40` (0x20 wchar, `memset(r15+0x42,0,0x3e)`+lead word),
    `fgetws(...,0x20,FILE*)`; output `r8+{0,0x18,0x30,0x4a,0x62,0x7a}` with
    `wcsncpy` maxima `12,12,13,12,12,13` wchar; callers only `0x004dd15e`,`0x004dd16c`
    in `fn 0x004dd028` (pool `0x004dd1e4`, no bsr, exhaustive dword scan). Builds
    on partial EXP-2026-11-05-M2.1-hddinfo-fn (C-720); C-721–C-728.
  - Claims: C-720–C-729

- [x] **M2.2 — The `SD Import: … is different` comparator**
  - Status: done · Owner: task/m2.2-sd-import-comparator · Critical: yes
  - Depends: — (M2.1 helps)
  - Goal: which fields are compared, against what, and with which checks.
  - Input: literals at `Navi.exe` `0x004e8584` / `0x004e995c`; the
    `Sys[0x%x]` vs `SD[0x%x]` formats; `tools/hddinfo.py` model M0.
  - Done when: each compared field is traced to a struct offset and a
    source (card vs system copy), and the `0 < userdata_type < 6` check is
    confirmed or refuted in this module.
  - Claims: C-730–C-739
  - Result: docs/experiments/EXP-2026-11-06-M2.2-sd-import-comparator.md (Navi.exe build A: `sub_004e84c4`/`sub_004e989c` validate `\UserSD\userdata\storedlocation.slc`/`homelocation.hlc` read by `sub_004df31c`; SD rec `r8+0x0c` destination_id vs caller `r15+0x18`, `+0x0e` manufacturer_id vs `r15+0x1a` [Sys refs upstream/unresolved], `+0x12` userdata_type `cmp/eq` const `0x1010`/`0x1011`, `+0x03` finished!=0, `+0x02` app type in `{1,0x21,0x31}`; `0 < userdata_type < 6` **refuted in this module**, C-730–C-739)

- [x] **M2.6 — Read `MapUpdate.exe` (image B)**
  - Status: done · Owner: task/m2.6-mapupdate · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: how the unit validates and installs map data; which files it
    checks and what it writes.
  - Input: `cerom.py --image-start 0x3e00200 IMG sections MapUpdate.exe`
    (file around `0x04344200`), its `imports`, strings.
  - Done when: `docs/format/firmware.md` has a "MapUpdate.exe" summary with
    function VAs, the files it opens, and every check it performs.
  - Claims: C-770–C-779
  - Result: docs/experiments/EXP-2026-11-06-M2.6-mapupdate.md; MapUpdate.exe summary in docs/format/firmware.md

- [x] **M2.7 — US vs EU market decision**
  - Status: done · Owner: task/m2.7-us-eu-market · Critical: no
  - Depends: — (registry part needs M1.4)
  - Goal: where the market/region is decided and whether an EU-format card
    can work in a US unit.
  - Input: strings and code in A/B/C, `ceconfig.h`/hives after M1.4,
    `docs/research/us-eu-region.md`.
  - Done when: an EXP names the deciding value(s) and module(s) and updates
    `us-eu-region.md`.
  - Claims: C-780–C-789
  - Result: docs/experiments/EXP-2026-11-06-M2.7-us-eu-market.md (Target ID byte `+5` → `commondll!CApi_GetModelArea` → `AppLaunch` launch mask; card cannot set area; C-780–C-789)

- [x] **M2.8 — SD card identity and lock (`SdCardLch.exe`)**
  - Status: done · Owner: task/m2.8-sdcard-lock · Critical: no
  - Depends: —
  - Goal: does the firmware check CID/CSD, an SD lock password or the FAT
    serial/label before using the card (`SD UNLOCK NG`)?
  - Input: `SdCardLch.exe` and `SDHC.dll` (find the image with `cerom.py
    modules` on A/B/C), their imports and strings.
  - Done when: an EXP lists every identity check with VA, and states which
    card properties a cloned card must reproduce.
  - Claims: C-790–C-799
  - Result: docs/experiments/EXP-2026-11-06-M2.8-sdcard-lock.md (SD lock password only; no CID/CSD/FAT serial/label check; C-790–C-799)

- [x] **M2.9 — Error-screen catalogue from firmware strings**
  - Status: done · Owner: task/m2.9-error-catalogue · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: for each error (`NAVI VERSION NG`, `DIFFERENT MAP CODE`, `MAP DATA
    BASE UNMATCH`, `SD UNLOCK NG`, others found), the module, string VA and
    the function that shows it.
  - Input: string search over all A/B/C modules (UTF-16 and ASCII),
    `cerom.py file2va`.
  - Done when: a table is in `docs/format/validation.md` (error → module →
    string VA → referencing function VA or `UNKNOWN`).
  - Claims: C-800–C-809
  - Result: docs/experiments/EXP-2026-11-05-M2.9-error-catalogue.md; catalogue in docs/format/validation.md

- [x] **M2.10 — What `TestMode.exe` (image C) can show or do**
  - Status: done · Owner: task/m2.10-testmode · Critical: no
  - Depends: —
  - Goal: find diagnostics relevant to map data (version screens, SD tests,
    map-code display, log dumps) usable later on the bench.
  - Input: `cerom.py --image-start 0x5200200 IMG sections TestMode.exe`,
    strings, imports.
  - Done when: an EXP lists the menus/functions with VAs and how test mode
    is entered (if found).
  - Claims: C-810–C-819
  - Result: EXP-2026-11-05-M2.10-testmode (menus/functions with VAs; entry via image C launch table + boot-mode flag; physical trigger unknown)

- [x] **M2.11 — When the unit reads `HDD_INFO.TXT` (`fn 0x004dd028`)**
  - Status: done · Owner: task/m2.11-hddinfo-trigger · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: know the trigger (boot, SD insert, menu) and the retry logic, so a
    test card is inserted at the right moment.
  - Input: `fn 0x004dd028` (calls `0x004e7b8c` twice, plus `Sleep` and
    `wcsncmp`, C-1710), its only reference: pool word `0x004dd2e4`
    (a dispatch/vtable entry); `sh4xref.py --to`.
  - Done when: the EXP names the table at `0x004dd2e4`, the caller of the
    entry, why the read is done twice, what the `Sleep` loop waits for, and
    what `wcsncmp` compares against (string at its literal).
  - Claims: C-1770–C-1779
  - Result: docs/experiments/EXP-2026-11-06-M2.11-hddinfo-trigger.md (trigger = NaviSetCC message 0x841000f7, not boot/SD insert; two reads = SystemSD vs UserSD; Sleep polls SDC1: IOCTL 0x80032004 state 4 six times; wcsncmp compares line 1; C-1770–C-1779)

- [x] **M2.14 — Unit NOR "EEPROM" area at `0x0000A000` (zelemar) vs our images**
  - Status: done · Owner: task/m2.14-nor-eeprom · Critical: no
  - Depends: — (M1.4 helps if a hive/config payload is found)
  - Goal: test, on data we actually have, the zelemar claim that the Clarion
    main MCU NOR flash (SST 38VF6401, SH-4A) keeps an "EEPROM area" at
    `0x0000A000` holding identification numbers, configuration data, the SD
    card password and other info (the password's last 12 bytes are ASCII
    `Clarion95321`).
  - Input: zelemar.eu "NISSAN LEAF SD card protection. How to obtain SD card
    password?" (hex view of EEPROM area) — treat as an external lead to verify,
    not as evidence; `IMG256` / `IMG` (Shared inputs); the 12-byte tail literal
    already found in `PRGUpdate.exe`/`TestMode.exe` (EXP-2026-11-06-M2.13) as a
    positive control. Note: `0xA000` is an offset in the *unit's* internal NOR
    dump, not in the SD card image — confirm whether our CE segments map to any
    NOR region or only to the card-resident ROM images.
  - Done when: an EXP (1) locates every occurrence of `Clarion95321` in
    `IMG256`/`IMG` (with file/VA via `cerom.py`) and compares context to the
    zelemar "EEPROM" fields, (2) states whether any bytes at/near a NOR-style
    `0xA000` anchor exist in the available images (with a control search that
    *can* find a known string), and (3) records the result as OBSERVED + a
    clearly labeled HYPOTHESIS or negative; `docs/research/sources.md` cites
    the article; no vendor bytes committed (offsets/counts/hashes/short header
    bytes only).
  - Result: EXP-2026-11-08-M2.14-nor-eeprom. Exhaustive search over EU/US 2011,
    EU 2014, EU 2016 SD images (positive control) finds 3 `Clarion95321` hits
    per image, all in IMG256: EU/US 2011 SD `0x042e5698` = B `PRGUpdate.exe`
    sec0 (VA `0x12498`, dataptr `0x884e4000`, uncompressed) via `cerom.py`;
    `0x057729f8` = C `TestMode.exe` sec0 (VA `0x157f8`, dataptr `0x8856e000`);
    `0x04ce5698` = byte-identical raw duplicate of PRGUpdate sec0, no o32 owner
    (OBSERVED/UNKNOWN). Contexts are SecurityCheck/ProductTestData/template
    literals, not 16-byte `[unit][Clarion95321]` NOR records. No NOR-style
    `0xA000` anchor/password record in available SD/CE images (negative);
    `0xA000` is unit NOR (SST 38VF6401) — card images contain no NOR dump, so
    zelemar NOR claim is HYPOTHESIS, not refuted. `sources.md` updated.
  - Claims: C-2000–C-2009

- [x] **M2.16 — `HDD_CHK.ATT` on real cards and `sub_0001e3f4`**
  - Status: done · Owner: task/m2.16-hddchk-att-realcards · Critical: no
  - Depends: — (M2.12)
  - Goal: M2.12 shows `HDD_CHK.ATT` is read only by `MapUpdate.exe`; confirm
    whether factory cards carry it at all and close the layout question.
  - Input: EU and US images (Shared inputs); `MapUpdate.exe!SilentAuthenticate`
    (B `0x0001c210`), `sub_0001e3f4`, `ctx+120`.
  - Done when: the EXP says per image whether `HDD_CHK.ATT` exists (path,
    size, SHA-256 only) and `sub_0001e3f4` is decoded or explicitly deferred
    with what blocks it.
  - Claims: C-2090–C-2099
  - Result: EXP-2026-11-06-M2.16-hddchk-att-realcards.md (`705cadb`, task/m2.16-hddchk-att-realcards); real EU/US cards checked for `HDD_CHK.ATT` and `sub_0001e3f4` decoded/deferred per EXP.

- [x] **M2.17 — `HDD_CHK.ATT` crypto context and the 0x582–0x5e8 range**
  - Status: done · Owner: task/m2.17-hddchk-crypto · Critical: no
  - Depends: — (M2.16 done)
  - Goal: M2.16 showed the updater's `sub_0001e3f4` is a crypto-context check
    (CRLF + ≥8 bytes in the first `0x80`), not a `memcmp`, and that no factory
    card ships the file. Without the generator, the updater path cannot be
    reproduced — which matters only if we ever ship an update.
  - Precheck: `grep -c HDD_CHK` in the extracted B modules, and `cerom.py
    sections MapUpdate.exe` so the crypto routines are known to be readable
    (they are: all executable sections are uncompressed, C-2128).
  - Scope: `MapUpdate.exe` (build B) only; the map path is closed (M2.12).
  - Input: EXP-2026-11-06-M2.16 (C-2090–C-2095; `*0x21300` ids 5/6,
    `sub_1e2d4`/`sub_1e330`, `0x1e6f8/834/9c0/aa0/ed9c`).
  - Done when: the 0x582–0x5e8 operand path is traced to its inputs, or the
    EXP states which device-side value (id 5 or 6) cannot be obtained without
    hardware and therefore blocks the generator.
  - Stop: after the two ids are traced; if both need device state, mark the
    generator `blocked` and stop.
  - Claims: C-2610–C-2619
  - Result: EXP-2026-11-08-M2.17-hddchk-crypto-ctx — `sub_1e3f4` `0x1e582–0x1e5e8`
    traced (decoded XOR id-5 @`0x1e582–590`, seed `[xored,~xored]` @`0x1e592–5aa`,
    file copy/ctx/`sub_1e330` call); id-5 = 8B (`sub_199b8`/`*0x21100` id=5),
    id-6 = 4B→8 hex (`sub_19978`/id=6); dispatch pointers `*0x21100/*0x21300/*0x21760`
    in **compressed** sec2 (runtime provider, unreadable statically, COREDLL/CEDDK
    only) — ids 5/6 unavailable without hardware/runtime. `SilentAuthenticate`
    reads `ctx+120` (20-hex, CRC16==0) from `caller->+8` subobj (`fn 0x1ccfc/0x1cee8`);
    `ctx+120` population/generation rule not statically closed. HDD_INFO path VA
    corrected (`0x4345e80`→module `0x12c80`, C-2616). **Generator blocked/not
    feasible** (missing id-5/id-6 outputs + ctx+120 rule + crypto binding + no
    sample). `docs/format/validation.md` updated; **M5.11 unaffected** (updater-only
    path, not Navi boot/map load).

- [x] **M4.25 — Regulation-word test: the no_* turns without a from-word, and the only_* encoding**
  - Status: done · Owner: task/m4.25-regulation-word-test · Critical: no
  - Depends: — (M4.23 tool)
  - Goal: explain why most `no_*` to-entries carry no from-word (`rd_restrictions.py match`: 152/411 and 128/235) and find the `only_*` encoding.
  - Precheck: `match --level 1` and `--level 2` on B48R058R reproduce 152/411 and 128/235.
  - Scope: B48R058R only; OSM side from the IMF; no writer.
  - Input: EXP-2026-11-08-M4.23-restriction-encoding (observations 12–13), the entry-class table of `match`.
  - Done when: each miss class is explained by a named, counted mapping check, or the same test passes (pre-stated PASS) on a second tile, or a negative EXP records it.
  - Stop: after one mapping audit and one second tile; otherwise `blocked` with the EXP.
  - Claims: C-2910–C-2919 (was C-2640–C-2649, collision fixed by H23)
  - Result: EXP-2026-11-08-M4.25-regulation-word-audit. Precheck reproduced 152/411 (L1) and 128/235 (L2) FAIL on B48R058R (`e9c9cb22…`). `rd_restrictions.py audit` (M4.25, B48R058R+dolnoslaskie IMF, L1/L2) partitions every `no_*` miss into named, counted classes (done-when satisfied): exclusive L1 208/259 `no_ff_word_naming_F_anywhere`, 21 ff-on-other-entry, 19 reverse-ff-on-F, 11 other-byte1-on-T (byte1 1/2/3); L2 90/107, 9, 7, 1. Dominant explanation = 0xff-naming-F word absent at the matched node (true encoding for that majority UNKNOWN), not nibble/position reversal. `only_*` encoding UNKNOWN with named negative candidates: "all other exits ff-naming-F" 148/240 L1, 138/193 L2 vs density 61.8%/74.5% and random-exit baseline 64.1%/74.7% (no separation); T/F/0xf markers and byte1 alternatives counted. Second-tile attempt (B48R050R/060R/068R/070R) found no n>=20 dolnoslaskie via coverage (0/3625). Pre-stated PASS still fails; claims C-2910–C-2917 (+2918–2919 reserved).

- [x] **M4.26 — Firmware reader VAs for section-2 grid kinds; LEV3456R level-4/5 parcel addressing**
  - Status: done · Owner: task/m4.26-sec2-lev3456-reader-vas · Critical: no
  - Depends: —
  - Goal: locate the reader of grid-tile section 2 (kinds `0x1046`/`0x2046`) and the consumer of the regulation words; find the parcel addressing of LEV3456R levels 4 and 5 (the writer's `clarion_bg.parcel_code` reproduces none of the 414 codes).
  - Precheck: `python3 tools/sh4xref.py` on the first 256 MiB of `archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` (image start `0x200200`) reproduces the RGD_DATA callers `0x00426cfc`, `0x00427870` of `docs/format/map-tiles.md`.
  - Scope: Navi.exe build A via `tools/cerom.py`; callers of RGD_DATA and MAP_DATA only, no new disassembly campaign.
  - Input: `docs/format/map-tiles.md` section table; C-870–C-872, C-887; EXP-2026-11-08-M4.23-restriction-encoding (observations 14–15).
  - Done when: a VA per kind (or UNKNOWN with a negative EXP), and a parcel-code function that reproduces every LEV3456R level-4/5 code.
  - Stop: after the RGD_DATA callers are traced; otherwise `blocked`.
  - Claims: C-2800–C-2809 (was C-2650–C-2659, collision with M1.15/M5.22/M5.23 fixed by H23)
  - Result: EXP-2026-11-08-M4.26-sec2-lev3456-reader-vas. Precheck reproduced RGD callers `0x00426cfc`/`0x00427870` and MAP callers `0x00426cfc`/`0x0042752c` (IMG256 `92aa525d…`). `0x426cfc` calls MAP_DATA `0x00425f40` then RGD_DATA `0x004266ec` (gated `*0x009e3e28`); `0x00427870` (RGD slot mgr, from `0x00427c90`) conditionally calls RGD_DATA. Section-2 routing (LEV sec2 kind `0x03e4`, grid kinds `0x1046`/`0x2046`) is read via RGD_DATA entry `0x004266ec` by role/callers (OBSERVED); per-kind internal dispatch and regulation-word consumer VA remain UNKNOWN (scoped). `lev3456_parcel_code(level,ay,ax)` (absolute coarse-grid, 20'/30' bit layout) reproduces **1911/1911** LEV3456R L4/L5 codes (sec1 62+1021, sec2 68+760 incl. 414 unique pair-codes); `clarion_bg.parcel_code` dir-relative = 0 (negative control). Claims C-2800–C-2807; `docs/format/map-tiles.md` updated.

---

- [x] **M3.4 — `DRSTR001.DAT` parser and what it validates**
  - Status: done · Owner: task/m3.4-drstr-parser · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: find the parser and list its checks (counts, ordering,
    sentinels, the leading `u32` = 47).
  - Input: re-run the filename search with real VAs: the old "map filenames
    have zero literal references" negative was made under the wrong
    address model, so search `DRSTR`, `CMP.LST`, `MAPAL` strings in
    `Navi.exe`, `NaviMapCC.dll`, `OBJDLL.dll`, `STDDLL.dll` and their xrefs.
  - Done when: a validation list is in `docs/format/drstr.md` with VAs, or
    an EXP shows the string search with a positive control and no xref.
  - Claims: C-850–C-859
  - Result: EXP-2026-11-06-M3.4-drstr-parser (DRSTR/CMP.LST xrefs in Navi.exe at 0x00419684/0x0041ba90; MAPAL only static table; no count/order/sentinel check identified)

- [x] **M3.9 — Name length limits and collation in the firmware**
  - Status: done · Owner: task/m3.9-name-collation · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: the rules a writer must follow for names (EXP-2026-11-05-M4.13
    left length limit and sort order UNKNOWN).
  - Input: imports of `wcscmp`/`_wcsicmp`/`CompareString`/`LCMapString`
    and their callers in name-search code (`Navi.exe`, `OBJDLL.dll`, search
    DLLs); any ISO-8859-2 → UTF-16 table; `tools/name_strings.py`.
  - Done when: the EXP names the compare function used for name search and
    its sort order (byte, locale, custom table), and any fixed buffer length
    for names, with VAs; `M4.13` writer rule updated in `refer.md` or the
    names doc.
  - Claims: C-1790–C-1799
  - Result: EXP-2026-11-06-M3.9-name-collation (C-1790–C-1799): name compare is `OBJDLL!OBJ_PntName_compare` `0x0349c540` → `STD_StringImp_compare` `0x03466ae0`; ordering is the custom weight table (`OBJ_Sort_cmpStr` `0x0349d3b4`, table `0x03485400`/`0x03485500`) and `STD_StringImp_comparePriority` `0x03467d84` for binary search; caps 32/64/128 chars; text is CP1252/Latin-1, not ISO-8859-2; `rdstm.md` writer rules updated.

- [x] **M3.17 — Which files can be copied verbatim to a Poland card**
  - Status: done · Owner: task/m3.17-verbatim-copy · Critical: no
  - Depends: H11
  - Goal: decide, with evidence, which files we never generate
    (`BICON001`, `OPNG`, `SPEECH`, `TMC`, `REFER002`, `RDSTM001`) and whether
    any of them carries region-specific content that must be emptied or
    rebuilt for Poland (e.g. US EV POIs in `REFER002`, US TMC tables).
  - Done when: each file has *copy / empty / generate* in
    `reader-coverage.md` with the reason; any *generate* gets a task.
  - Claims: C-2220–C-2229
  - Result: EXP-2026-11-08-M3.17-verbatim-copy (C-2220–C-2229). EU-base Poland:
    `BICON001`/`OPNG`/`SPEECH`/EU `TMC` **copy** (assets/market config);
    `REFER002` **copy** EU market-correct (never US→EU; no empty without reader
    evidence, EV schema undecoded); `RDSTM001.DAT`+`LCTBL001.DAT` **generate**
    (M5.19, M5.17). `COORD001`/`ZCODE0nn`/`ICODE001` copy-eligible (G6).
    `reader-coverage.md` rows 7–9,21–22,24–28 updated; no new task required.

- [x] **M3.20 — Name the register-AND mask variant; correct the M3.11 pattern text**
  - Status: done · Owner: task/m3.20-mask-pair-via-reg-r2 · Critical: yes
  - Depends: M3.19 (blocked; M3.20 is M3.19's unblock task — dep verified
    honestly: `tools/sh4scan.py` and M3.19's finding/site exist; via-reg
    variant added here)
  - Goal: M3.11 §2 reports `and #0x70,r0` then `cmp/eq #0x60` as 1 hit in build
    A. The one site is `mov #0x70,R3; and R3,R0; cmp/eq #0x60,R0`
    (Navi.exe `0x3715c8–0x3715cc`), a register AND that the immediate pattern
    cannot match (EXP-2026-11-08-M3.19-sh4scan §5).
  - Precheck: `python3 tools/sh4scan.py IMG --image-start 0x200200 dump --module Navi.exe --va 0x3715c0 --count 8`
    shows those three halfwords. (Verified on IMG256 `92aa525d…`.)
  - Scope: `tools/sh4scan.py` (`mask-pair --via-reg`, stdlib + selftest);
    build A uncompressed sections; M3.11 EXP §2 pattern-text correction and
    C-2560–C-2569 claim rows (M3.20 done-when). No other task's lines.
  - Done when: `mask-pair --via-reg --cmp 60` runs on `IMAGE_START 0x200200`,
    its selftest pins the variant, and M3.11's pattern text is corrected by a
    new claim row (no deletion, per the ledger rules). The count is the result,
    not a precondition: report whatever it is.
  - Stop: if the variant count is not 1, record it in an EXP and stop.
  - Result: EXP-2026-11-08-M3.20-mask-pair-via-reg (C-2560–C-2562). `sh4scan`
    selftest OK (section 4b pins register-AND). `mask-pair --via-reg --cmp 60`
    on build A (IMG256 `92aa525d…`, 282 uncompressed / 527 sections) found
    **1** site: Navi.exe sec0 `mov @0x003715c8 and @0x003715ca cmp @0x003715cc
    R3 (+4 B)`. M3.11 EXP §2 pattern text corrected (immediate → register-AND)
    and C-2560 added (no deletion). No vendor bytes committed.
  - Claims: C-2560–C-2569

- [x] **M4.4 — Tile section 4 under a road edit**
  - Status: done · Owner: task/m4.4-section4-road-edit · Critical: no
  - Result: EXP-2026-11-06-M4.4-section4-road-edit; in-place one-vertex road edit of B30R048R.DAT changes 116 bytes and keeps section 4 byte-identical (20 records / 68 names, sha256 4cbf...); harness verify and l2check --no-golden PASS
  - Depends: —
  - Goal: prove section 4 (place-name index, `section4.py`) can stay
    verbatim when roads change, or map the fields that must change.
  - Input: `tools/section4.py preserve/verify`, `harness.py mutate`.
  - Done when: a one-tile road edit with verbatim section 4 passes L2 and
    the EXP states which section-4 fields depend on road content (or none).
  - Claims: C-920–C-929

- [x] **M4.5 — `MMAIN001.DAT` meaning and writer**
  - Status: done · Owner: task/m4.5-mmain001 · Critical: no
  - Result: EXP-2026-11-05-M4.5-mmain001 (`tools/mmain.py`; a FAT root-directory log, 51 records, 12 live; round-trip OK; the task said 11 entries)
  - Correction (EXP-2026-11-06-H6): `tools/mmain.py` parsed the FAT root
    directory, not `MMAIN001.DAT`; the real 4 KiB header is described in
    `drstr.md`. The "FAT log" reading is retracted; H8 re-scopes the tool.
  - Depends: —
  - Done when: a writer reproduces the 4,096-byte file (11 entries)
    byte-identically and every field has a meaning or `UNKNOWN`.
  - Claims: C-930–C-939

- [x] **M4.6 — The `B30R048R` 2013–2016 rebuild difference**
  - Status: done · Owner: task/m4.6-b30r048r-diff · Critical: no
  - Depends: —
  - Input: EXP-30, `tools/diff_years.py`, 2014/2016 roots.
  - Done when: the difference at `0x807`/`0x808` is explained and the writer
    needs no fallback.
  - Claims: C-940–C-949
  - Result: EXP-2026-11-05-M4.6-b30r048r-diff; non-monotonic shared-block layout + non-canonical addr_of tags; clarion_tile.write_tile now byte-identical for 2011/2014/2016 (preserved=0)

- [x] **M4.7 — Rename path for names/addresses**
  - Status: done · Owner: task/m4.7-rename-path · Critical: no
  - Depends: —
  - Input: `ADDRE`/`POINT`/`ZCODE`/`LCTBL` (`docs/format/refer.md`,
    `tools/mutate_refer_poi.py`, `tools/lctbl_names.py`).
  - Done when: a renamed POI with a different-length name passes L2.
  - Result: `POINT` name pages are `tag,len2` record chains; `--resize` patches
    `len2` and shifts the page, and the new L2 `refer_rename_resize` check
    passes on 2011 (POINT032, +4) and 2014 (POINT002, 1,000 records)
    (EXP-2026-11-06-M4.7-poi-rename-resize). `ADDRE`/`LCTBL` remain open
    (C-957, C-958).
  - Claims: C-950–C-959

- [x] **M4.9 — `ADDRE` remaining grammar**
  - Status: done · Owner: task/m4.9-addre-grammar · Critical: no
  - Depends: —
  - Goal: 6-/12-byte index cells, `c0` vs `c8` grammar, subtypes
    `0x54`/`0x58`, `40 XX YY` point encoding, trailer table.
  - Done when: each item is decoded or `UNKNOWN` with a method in
    `refer.md`, with a test on a synthetic record.
  - Result: 12-byte directory, 6-byte cell framing, `c0`/`c8`, name section,
    range slots and the trailer TOC are decoded; cell payload and point
    arithmetic are `UNKNOWN` with controls. `tools/addre.py` (14/14 checks on
    001/017/003). EXP-2026-11-06-M4.9-addre-grammar.
  - Claims: C-970–C-979

- [x] **M4.10 — POI icon code → `BICON001` PNG**
  - Status: done · Owner: task/m4.10-poi-icon · Critical: no
  - Depends: —
  - Done when: a mapping table for ≥ 20 POI categories is in
    `docs/format/assets.md` (icons are not committed).
  - Claims: C-980–C-989
  - Result: EXP-2026-11-06-M4.10-poi-icons; 34-row table in `assets.md`;
    `tools/poi_icons.py` reproduces the scan

- [x] **M4.13 — Strings: length limits, collation, Polish diacritics**
  - Status: done · Owner: task/m4.13-strings · Critical: no
  - Result: EXP-2026-11-05-M4.13-strings (`tools/name_strings.py`; 297,295 text strings in 517 streams; decode errors 0; Polish letters present; writer rule: reject non-Latin-2; collation UNKNOWN)
  - Depends: —
  - Goal: max name length per field, character set, sort order and whether
    `ą ę ł ń ó ś ź ż` are representable (Czech/German names in the EU image
    are the control).
  - Done when: an EXP with counts per field and a charset table, and the
    IMF/writer rule for unsupported characters.
  - Claims: C-1010–C-1019

- [x] **M4.14 — Cross-year and cross-market archive**
  - Status: done · Owner: task/m4.14-cross-year-archive · Critical: no
  - Result: docs/research/image-versions.md inventory + fields table; docs/experiments/EXP-2026-11-06-M4.14-cross-year-archive.md; claims C-1020–C-1029
  - Depends: —
  - Goal: a table of every image on `files.viaaq.eu` (year, market, map
    code, `HDD_INFO`, header versions, tile counts) via `diff_years.py`.
  - Done when: `docs/research/image-versions.md` has the table with SHA-256
    per image and the fields that change with the map code.
  - Claims: C-1020–C-1029

- [x] **M4.19 — `(XX, YY)` point coordinate arithmetic**
  - Status: done · Owner: task/m4.19-addre-point-coords · Critical: no
  - Depends: — (M4.9 leaves this `UNKNOWN`; M4.12 helps)
  - Goal: turn the `40 XX YY` point token into a geographic coordinate, the
    last missing piece between an ADDRE record and a map position.
  - Input: `tools/addre.py` (`cells`, `records`, `stats`),
    `docs/format/refer.md` ADDRE section, point tags `02..05` with the
    `40 XX YY` payload on `ADDRE001`/`017`/`003`, `COORD001` region boxes,
    `POINT0nn` coordinates; the Monaco box is degenerate, so pick a second
    country as the control.
  - Done when: the `(XX, YY)` → latitude/longitude (or tile/mesh position)
    mapping is decoded with a control that fails on a wrong hypothesis, or
    it is proven not derivable from these fields alone with the method
    recorded; `refer.md` and `tools/addre.py` carry the rule and a synthetic
    test.
  - Claims: C-1960–C-1969
  - Result: EXP-2026-11-06-M4.19-addre-point-coords. 2D geographic `(lat,lon)`
    not derivable from `(coord,XX,YY,tag)` alone (C-1964, supersedes C-976
    arithmetic / narrows C-979): `YY` 0–255 full, `XX` shard-capped (23/50/58),
    95–98 % same-`XX` simple pairs contradicts fixed 2D geographic axes;
    controls: whole-unit `cx+XX,cy+YY` 14.0 % in Andorra box (~4 km segs, wrong)
    vs 1/256 candidate 100 % (~16 m, scale only, not verified 2D). Monaco box
    degenerate (non-discriminating). No independent 2D anchor from these fields.
    `refer.md` + `tools/addre.py` (`assess_point_coords`, `--selftest`) carry the
    rule.

- [x] **M4.21 — Tile section-4 writer (place-name index, H11 G3)**
  - Status: done · Owner: task/m4.21-section4-writer · Critical: no
  - Depends: M3.6 (who consumes it), M4.4 (preserve path)
  - Goal: `section4.py build` refuses (exit 3) and every tile edit so far
    keeps section 4 verbatim, so a tile whose place names must change — any
    generated Dolnośląskie tile — cannot be written.
  - Input: `tools/section4.py` (`parse`/`verify`/`build`), EXP-2026-11-06-M4.4
    (preserve under a road edit; 20 records / 68 names), the undisclosed bytes
    `0x06..0x0f`, M3.6's answer on the section-4 consumer, 2011/2014/2016
    samples.
  - Done when: `section4.py build` writes a section 4 for a changed parcel set
    that `verify` accepts and `l2check` passes on all three years, or the EXP
    shows with a control that the section is never read and `--empty` is safe.
  - Claims: C-2390–C-2399
  - Result: `section4.py build` now works (patch mode preserves 0x06..0x0f/names/opaque; unchanged records keep original compressed bytes; changed recompress L6/w15/m8) and refuses only on names with no `payload_hex`. `generate` produces verify-accepted nameless payloads for changed parcel sets. `verify` accepts on EU2011/2014/2016 B30R048R; EU2011 factory l2check baseline PASS; 2014/2016 harness round-trip OK (H14 pre-existing notes). M3.6 control: no read VA in traced MAP/RGD/loader; tiles without sec4 exist. Full 2014/2016 `l2check --root` on regenerated sec4 needs complete extracted roots (documented). EXP-2026-11-08-M4.21-section4-writer.md, C-2390–C-2395.

- [x] **M4.30 — Restriction word-test deepening: class-dependent encoding and mapping errors (M4.23 follow-up)**
  - Status: done · Owner: task/m4.30-restriction-deepening · Critical: no
  - Depends: M4.23 (findings), M4.25 (word-test audit task)
  - Goal: turn M4.23's real-but-below-threshold signal into an actionable
    encoding hypothesis for M4.3/routing. M4.23 found `no_*` to-entry carries
    the from-word on 37 % (L1) / 55 % (L2) overall vs 4 % / 3 % shuffled, but
    arrival→exit reached 65 % / 71 %; 63 % missing cases were unexplained
    (candidates: mapping errors from way splits at via/two-way entries, a
    different encoding for part of the population, level-1 graph missing
    junctions).
  - Precheck: reproduce M4.23's `rd_restrictions.py match` summary numbers on
    `B48R058R` + `dolnoslaskie.imf.jsonl` (or the recorded corpus) so the
    baseline is pinned.
  - Scope: analysis on the M4.23 corpus first; stratify by entry class
    (arrival/exit/two-way), detect way-split-at-via and ambiguous bearing
    matches, and test whether the remaining misses cluster by restriction type,
    one-way geometry, or a second word position/form. Coordinate with M4.25 so
    work is not duplicated.
  - Done when: the EXP reports hit rates per stratum with controls, names the
    dominant miss causes with counts, and either (a) proposes a specific
    encoding rule that reaches the pre-stated threshold on a held-out subset or
    (b) shows with controls that no single rule fits and files the split
    hypotheses as follow-ups.
  - Stop: do not lower the pass threshold; a better model or an honest split is
    the result.
  - Claims: C-2890–C-2899 (was C-2770–C-2779, collision with H27 fixed by H23)
  - Result: EXP-2026-11-08-M4.30-restriction-deepening (result b). Precheck reproduced M4.23/M4.25 baselines (L1 152/411/18, L2 128/235/8, FAIL). `rd_restrictions.py deepen` (M4.30, `--selftest` 17 checks, `claims_check` clean) stratified by entry class with per-stratum shuffle/match-order RNG and held-out (sha256 relation id mod2, bucket1=test, no outcome fitting): no pre-defined stratum reaches PASS on held-out n>=20 (L1/L2). L2 `two->lv` 22/18 (81.8%) PASS full but test n=13/10 FAIL (n<20); `arr->lv` L1 68/44 (64.7%) test 32/20, L2 75/53 (70.7%) test 38/29 (76.3%). Mapping: 851/1317 bearing exclusions = 492/737 count mismatch + 359/580 angle; matched `no_*` dup-way 0, `osm_from_eq_to` 106/41, ambiguous `<15°` 32/51. Misses (259/107) dominated by `no_ff_word_naming_F_anywhere` 208/90 (M4.25); `two->two` concentrates `no_u_turn`+`osm_from_eq_to` (103/101 L1). No single rule fits pre-stated PASS on held-out (b); split hypotheses filed as M4.32–M4.34. Claims C-2890–C-2895.

- [x] **M4.32 — Direction-explicit restriction stratum: combined `arr->lv`/`two->lv` rule with held-out n>=20 (M4.30 follow-up)**
  - Status: done · Owner: task/m4.32-direction-explicit-stratum · Critical: no
  - Depends: M4.30 (findings)
  - Goal: test whether a pre-defined combined direction-explicit stratum (`arr->lv`+`two->lv`, 0xff-on-T-naming-F plus named M4.25 variants as pre-specified) reaches pre-stated PASS on a held-out subset with n>=20 (pool L1+L2 or larger corpus) and explain residual `no_ff_word_naming_F_anywhere` misses via second word position/form or junction-mapping audit.
  - Precheck: reproduce M4.30 `deepen` `arr->lv`/`two->lv` numbers (L1 68/44, 31/21; L2 75/53, 22/18) — reproduced.
  - Result: EXP-2026-11-08-M4.32-direction-explicit-stratum (result b with decomposition). Pre-specified full union (base + M4.25 v1 reverse/v2 other-byte1-on-T/v3 ff-on-other-entry) fails pre-stated PASS on held-out n>=20 (sha256 id mod2, bucket1=test) due to v3's structurally non-discriminating shuffle analog (L1 41/51 hit 80.4% but shuffle 72.5%; L2 42/51 82.4% shuffle 76.5%; pooled 83/102 81.4% shuffle 74.5%). Discriminating decomposition `base+v1+v2` reaches PASS on L2 held-out (42/51=82.4%, shuffle 2.0%) and pooled L1+L2 held-out (82/102=80.4%, shuffle 4.9%, 57 overlapping IDs — not independent); L1 held-out 40/51 (78.4%) miss. Union residuals `no_ff_word_naming_F_anywhere` (41 total, 19 test) dominated by T-empty/T-has-ff-naming-other; junction-mapping signals (0 from==to/dup, 7/41 amb<15°) do not explain them. `rd_restrictions.py direction` added (`--selftest` 23 checks), `claims_check` clean. Rule 13: not firmware-confirmed. Claims C-3010–C-3015.
  - Claims: C-3010–C-3019

- [x] **M4.33 — `two->two`/`no_u_turn`/`osm_from_eq_to` restriction geometry/mapping class (M4.30 follow-up)**
  - Status: done · Owner: task/m4.33-twotwo-u-turn-mapping · Critical: no
  - Depends: M4.30 (findings), M4.25
  - Goal: per-case/counted audit of same-way identity, u-turn representation, and OSM-vs-tile way splitting at via for the `two->two` miss class (dominated by `no_u_turn`/`osm_from_eq_to` and absent 0xff-naming-F); determine if mapping normalization or an alternate encoding applies.
  - Precheck: reproduce M4.30 `two->two` miss clustering (L1 188 misses: `no_u_turn` 103, `osm_from_eq_to` 101, `no_ff_word_naming_F_anywhere` 157).
  - Scope: matched `no_*` `two->two` stratum on B48R058R/dolnoslaskie IMF (same M4.30 corpus), levels 1 (precheck) and 2 (pattern control), via `_deep_rows` pipeline; read-only. Excludes bearing/count-mismatch exclusions (492/737, M4.34), other tiles/IMF, `only_*`, levels 4/5, firmware consumer VAs (rule 13), and per-relation manual OSM geometry beyond named tool fields.
  - Done when: precheck reproduced and EXP reports counted feq/F==T identity, u-turn representation (including tested self-form `F_names_F_ff`), splitting/mapping-shape signals, and a determination on mapping normalization vs alternate encoding with named residuals/controls.
  - Stop: if precheck cannot be reproduced on the pinned corpus, record the discrepancy and stop.
  - Claims: C-2990–C-2999
  - Result: EXP-2026-11-08-M4.33-twotwo-u-turn-mapping. Precheck reproduced (L1 188: 103/101/157; L2 61: 38/37/54). `tools/m433_twotwo_audit.py` (no `rd_restrictions.py` changes) shows `osm_from_eq_to` == `F==T` are identical sets in `two->two` misses (L1 101/101, L2 37/37; 0 in hits), all feq are `no_u_turn`; tested self-prohibition `F_names_F_ff` is 0 for feq/F==T (L1 0/101, L2 0/37); `no_u_turn` hits only when !feq/F!=T (4/5). Matched `dup_way` 0, `amb_margin<15` 0/188 L1 (3/61 L2) — representational same-way→same-entry class, not bearing-split in matched set. Mapping normalization cannot separate F==T under same bearing; tested self-ff encoding negative; alternate encoding/location/absence remains UNKNOWN pending firmware consumer VA (rule 13, M4.26/C-2805/C-2629). Claims C-2990–C-2994.

- [x] **M4.34 — Bearing count-mismatch exclusion analysis for restriction matching (M4.30 follow-up)**
  - Status: done · Owner: task/m4.34-bearing-count-mismatch · Critical: no
  - Depends: M4.30 (findings)
  - Goal: classify 492/737 L1/L2 count mismatches (OSM bearings != tile non-edge entries) — OSM through-way extra bearings, tile far-node-in-other-record filtering, or genuine junction mismatch — and quantify recoverable matched population without outcome fitting.
  - Precheck: reproduce M4.30 mapping diagnostics (L1 492 count + 359 angle of 851; L2 737+580 of 1317).
  - Scope: analysis on the M4.30/M4.23 `B48R058R` + `dolnoslaskie.imf.jsonl` corpus, levels 1 and 2 only; count-mismatch exclusions only (492 L1, 737 L2). No changes to `tools/rd_restrictions.py`; if code is needed, add a uniquely named `tools/m434_bearing_mismatch.py`. No vendor bytes committed.
  - Done when: the EXP reports, with controls and without outcome fitting, counted classes for the 492/737 count mismatches (OSM through-way extra bearings, tile far-node-in-other-record filtering / record-boundary differences, genuine junction mismatch, other/unclassified) and quantifies the recoverable matched population implied by each class; precheck diagnostics are reproduced; follow-ups named if recovery needs a rule change.
  - Stop: do not fit outcomes to raise counts; if a class cannot be distinguished on available data, count it as unclassified with the reason and stop.
  - Claims: C-3000–C-3009
  - Result: EXP-2026-11-08-M4.34-bearing-count-mismatch. Precheck reproduced (L1 492+359/851, L2 737+580/1317). `tools/m434_bearing_mismatch.py` (11 selftest checks, no outcome fitting) classifies `osm!=tile2`: mostly `osm_more` with extra non-from/to bearings (361/492 L1, 622/737 L2); pass-through rare (7/3). Tile far-node-in-other-record filtering ruled out for this class by construction (separate `tb!=nonedge` branch). `junction_dist>4` 174/205 (weak indicator). Geometric from/to subset recoverable 161/492 (32.7%) L1, 173/737 (23.5%) L2 (no rule adopted). Claims C-3000–C-3005.

- [x] **M5.8 — One-tile diff report**
  - Status: done · Owner: task/m5.8-tile-diff · Critical: no
  - Depends: —
  - Goal: an automatic report of what changed vs what was preserved between a
    factory and a generated/mutated tile (sections, records, bytes).
  - Input: `harness.py compare-tiles`, `section4.py`.
  - Done when: `tools/tile_diff.py A B --json` works on a factory tile and on
    the `harness.py mutate` output.
  - Claims: C-1100–C-1109
  - Result: EXP-2026-11-05-M5.8-tile-diff (`tools/tile_diff.py`; factory vs mutate output: 148 bytes in 2 ranges; `tools_ze0` package committed as `tools/ze0-viewer/tools_ze0/`)

- [x] **M5.9 — `tile_diff.py`: match moved streams and name the records**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: —
  - Goal: a generated tile's diff reads as "changed record X", not as
    remove + add at another offset.
  - Input: `tools/tile_diff.py` (offset-based matching), `tools_ze0`
    (`clarion_tile.py` section/record layout), `section4.py`.
  - Done when: on the M5.8 mutate output the report shows 1 changed stream
    (0 added/removed) and the level/record/vertex that changed; self-test
    covers a moved stream.
  - Result: content-hash matching + structural record naming; a moved+changed
    record is one `changed` entry, `--by-offset` keeps the old view
    (EXP-2026-11-06-M5.9-tile-diff); factory-vs-mutate pending.
  - Claims: C-1850–C-1859

- [x] **M5.12 — Rename a POI (or place name) on the US card image**
  - Status: done · Owner: task/m5.12-us-poi-rename · Critical: yes
  - Depends: M5.10 (M4.8c helps locate the target)
  - Goal: the near-term milestone — one on-screen name changed in the US map,
    on a rebuilt card image, checked offline, ready for Marek's unit. A name
    change is picked over a moved road because it is the most visible edit and
    the rename path is already proven (M4.7 passes L2, different length too).
  - Input: `LEAF_2011-2012_US.img` (= Marek's own card) from
    `https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img` (extract `ROOT`
    with `tools/verify.py --image`); the rename tooling from M4.7
    (`tools/mutate_refer_poi.py`, `tools/lctbl_names.py`, `docs/format/refer.md`);
    `tools/section4.py` (place-name index), `tools/tile_diff.py`,
    `tools/mkcard.py` (M5.10). The target POI/place is Marek's choice (he must
    recognise it on screen); M4.8c/`coord.py` confirm which tile holds it.
    No vendor bytes committed (offsets/counts/hashes only).
  - Done when: one POI or place name in a US tile is changed (a plain example:
    swap a city/POI label for a clearly different ASCII string) and L2 passes;
    `tile_diff.py` shows only the name change; `mkcard.py` rebuilds the card
    image and `cardcheck.py --image` passes; the EXP names the tile, the
    original name and the new one so Marek can confirm it on the unit. If a
    place name touches section 4 or the name DB in a way M4.7 did not cover,
    record what changed and fall back to a POI rename (the proven path).
  - Result: EXP-2026-11-06-M5.12-us-poi-rename.md — US image `53342430…c5383`
    (8,057,257,984 B). REFER001/POINT010.DAT, inner page `0x840ba0`, record 0
    (`tag=0x60,len2=64,total=128`): renamed **`HANA HEALTH CENTER` →
    `OSM2LEAF TEST POI1`** (18 B, same length; decompressed name bytes differ,
    logical size/DRSTR unchanged). `validate_mutation.py` PASS; `cmpind.py
    verify REFER001` 58/58 OK; `l2check.py --no-golden --skip-mutation
    --ignore-dump-artifacts --no-tiles` (TMPDIR on leafre-work) `cmp_roundtrip`
    58/58 OK (DRSTR round-trip diff at 0x1ae0 matches unmodified US factory,
    pre-existing, not regression; EU golden/tiles inapplicable). `mkcard.py`
    rebuilt `us_m5.12_renamed.img`; `cardcheck.py --image` **PASS** (exit 0,
    113 tiles, 58 pairs, DRSTR OK, `image_copy=identical`). Tool fixes kept:
    `mutate_refer_poi.py` L9 fallback, `mkcard.py` LFN slot order (selftests).
  - Claims: C-1980–C-1989

- [x] **M5.22 — Tile writer: model non-`0x2046` directory kinds**
  - Status: done · Owner: task/m5.22-tilewriter-non2046 · Critical: yes
  - Depends: M5.4 (done)
  - Goal: M5.4 splices only `0x2046` directories (18 parcels in `B48R058R`)
    and refuses other kinds; 575 of 1,023 non-`0x2046` slots in that tile are
    "unclean" under the current model. Any cell with those directories cannot
    be fully written until their slot table is understood.
  - Precheck: run `harness.py verify`/the M5.4 parser on `B48R058R` and record
    which directory kinds fail and how (counts, the invariant).
  - Scope: the directory slot table for the failing kinds (e.g. `0x2146`) in
    the five pinned tiles; writer refuses unchanged kinds.
  - Input: EXP-2026-11-08-M5.4-tile-splice (C-1064), `tools/ze0-viewer` parser,
    `tools/tilewriter.py`.
  - Done when: the slot table for the failing kinds is modelled, `tilewriter.py`
    can splice or safely preserve them with a `--selftest` case, and L2 passes
    on a real tile that contains the kind; or the kind is documented as
    opaque-preserve-only with the invariant that justifies it.
  - Stop: if a kind needs reader semantics the parser does not have, record it
    and keep the writer in refuse/preserve mode for that kind.
  - Result: preserve-only branch satisfied. EU 2011 sec1 lv1 `0x2n46` kinds
    (0x2146/2246/2346/2446/2546/2646/2746/2946, observed B48R058R/B30R048R;
    5 pinned + B48R058R `clarion_tile` round-trip byte-identical) have a
    modelled container (header/tags/512-byte pair bodies/declared tail) but
    often non-zlib / `X=0xffffffff` pair fields make record boundaries unsafe
    for mutation. `tools/tilewriter.py` now classifies 0x2046 spliceable and
    0x2x46 preserve-only (mutation refused with invariant), detects same-offset
    block aliasing in `shared_slot_blocks`, and `verify_factory` checks
    preserve-only dir bytes unchanged. `--selftest` 59/59; M5.4 B48R058R splice
    reproduced byte-identical (`a1292979…`) and `l2check --no-golden
    --skip-mutation` PASS on the real tile containing those kinds.
    EXP-2026-11-08-M5.22-tilewriter-non2046.
  - Claims: C-2810–C-2814 (was C-2650–C-2659, collision with M1.15/M4.26/M5.23 fixed by H23)

- [x] **M5.25 — Reconcile REFER POI page encoding (slot_budget vs mutate_refer_poi/M5.12c)**
  - Status: done · Owner: task/m5.25-reconcile-poi-page-encoding · Critical: yes
  - Depends: M5.12c (blocked: uncompressed-files scan unfinished), M1.16, M5.21
  - Goal: one safe path for editing/writing POI name pages on a real card.
    M5.21 (`slot_budget.py`) implements its own slot rule and encoder search and
    notes "two slot rules... written twice; reconciling belongs to the M5.12c
    owner"; `mutate_refer_poi.py` on `main` lacks the M5.12c refit/FitError path
    while M5.12c is blocked. Divergence here can overflow a slot or miss copies
    — both break the nearest milestone (Marek's S1/S2/S3 bench runs depend on
    predictable, minimal diffs).
  - Precheck: `git show --name-only claude/m5.12c-poi-copies` (or the M5.12c
    branch state) and the M5.21 EXP scope limits identify the exact API/behavior
    differences; `python3 tools/slot_budget.py --selftest` and
    `python3 tools/mutate_refer_poi.py --help` on `main` establish baselines.
  - Scope: `tools/mutate_refer_poi.py`, `tools/slot_budget.py`, `tools/poi_copies.py`
    (and shared codec from M1.16 if landed). No new format claims; this is
    integration/refactoring. Preserve M5.21's "refuse and list, never overflow"
    contract and M5.12c's "find every copy" goal.
  - Done when: one documented entrypoint (or a thin wrapper) performs same-length
    and refit edits with the M5.21 slot budget, uses factory params from M1.13/
    M1.16, refuses pages that cannot fit, reports every refused page and (once
    M5.12c unblocks) every name copy; existing selftests still pass and a new
    synthetic test covers an over-budget refusal and a fitting refit.
  - Stop: if M5.12c's unmerged branch cannot be reconciled without guessing its
    intent, record the diff and keep M5.12c as the unblock; do not silently drop
    its scan behavior.
  - Unblock: M5.12c (for the "every copy / uncompressed scan" part); the slot/refit
    API reconciliation can proceed once M1.16 defines the shared codec.
  - Claims: C-2870–C-2879 (was C-2750–C-2759, collision with H25 fixed by H23; none registered, integration/refactoring)
  - Result: EXP-2026-11-08-M5.25-reconcile-poi-page-encoding. Reconciled `mutate_refer_poi.py`/`slot_budget.py`/`poi_copies.py` into one safe path: `mutate_refer_poi.py` is the documented entrypoint for same-length+refit edits using M5.21 slot budget (`--headroom`, batch default 0.04 / single default 0.0), factory params M1.13/M1.16 via `cmpind_codec`/`slot_budget`, refuses and reports every refused page with budget rows (`*.skipped.json`), never overflows (synthetic negative). `slot_budget.FitError`/wide reproduction search (M5.12c unchanged-bytes intent) aligned; M5.12c branch diff recorded, no merge/guessing, scan behavior not dropped (`poi_copies.py --inner`, `--copies-report`). "Every name copy" enumeration remains blocked on M5.27/M5.12c uncompressed scan (Done when conditional). `slot_budget 14/14`, `mutate_refer_poi 10/10` (+over-budget refusal/fitting refit), `poi_copies OK`, `cmpind_codec 21`, `claims_check OK`.

- [x] **M6.3 — Spare-card test plan**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: — (M2.8 refines it)
  - Done when: `docs/research/card-test-plan.md` defines the whole-card
    clone, the no-op control, then one changed tile, with pass/fail
    criteria and what to photograph.
  - Result: `docs/research/card-test-plan.md` (S0 clone, S1 no-op
    recompression, S2 POI rename, S3 tile, S4 map-code) with pass/fail,
    rollback and photo checklist (EXP-2026-11-06-M6.3-card-plan).
  - Claims: C-1110–C-1119

- [x] **M6.4 — Recovery checklist**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: M2.6
  - Done when: a checklist for returning the unit to the factory map is in
    the test plan.
  - Result: recovery checklist in `card-test-plan.md`: signatures, ordered path, static/hearsay/untested split (EXP-2026-11-06-M6.4-recovery).
  - Claims: C-1120–C-1129

- [x] **M6.8 — Bench kit list and serial/JTAG access plan**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: — (M8.A6 for the debug UART)
  - Goal: what to buy and wire (12 V supply, `TEST_B1`, CAN simulator, SD
    extender, UART at the SCIF `0xffe46000` pins if found).
  - Done when: a parts list with costs and a wiring note is in
    `docs/research/dynamic-break-guide.md`.
  - Result: bench kit + access order in `dynamic-break-guide.md`; prices
    ESTIMATE, SCIF pins UNKNOWN (EXP-2026-11-06-M6.8-bench-kit).
  - Claims: C-1130–C-1139

- [x] **M6.12 — Clarion debug console (MONI `FW>`, `DSW=0006`) access procedure**
  - Status: done · Owner: session-ZMxuBT · Critical: no · **Runner: non-Claude** (needs
    hardware; planning is doable now, the procedure is unverified until bench)
  - Depends: M6.8 (bench kit / access plan); complements M8.A6 and
    `docs/research/dynamic-break-guide.md`
  - Goal: a tested, step-by-step procedure to reach the Clarion firmware monitor
    on ZE0-era units and use it for memory reads / dumps relevant to map/auth
    work (a fallback/companion to the dynamic breaks plan).
  - Input: zelemar.eu "SD Card Toolbox – Nissan Leaf navigation interface"
    (debug interface, `Rx`/`Tx`/Mode select, no disassembly needed; TE
    Connectivity **1674312-1**; MONI mode `DSW=0006` → `FW>` prompt; commands
    `?`/`h`, `r`, `g`, `mb/mh/mw` [read memory], `e`, `s`, `w/wr`, `m1/m2`,
    `cb/ch/cw`, `mv`; modes/prompts confirmed in comments: `FACT`/`NORM(EVA)`→
    `>>`, `MONI`→`FW>`, `PROD`→`clarion>`); zelemar.eu "NISSAN CAN filter
    installation" (Vehicle I/F + signal connector pinouts:
    `nissan-leaf-signal-connector.jpg`, `nissan-leaf-power-connector.jpg`);
    `docs/research/dynamic-break-guide.md`; M6.8 bench kit. Note hardware
    variance from comments: QY5017HC uses SST38VF6401 (WinCE+XIP), QY8602/QY8350
    use MICRON PC28F512 with no 2nd SD — confirm unit model before assuming a
    layout.
  - Done when: `docs/research/dynamic-break-guide.md` (or a linked note) has a
    procedure listing the connector pins, level-shifting/wiring, mode-select
    setting, baud/terminal settings (or `UNKNOWN` with how to measure), and the
    safe read-only command subset (`mb/mh/mw`, `r`) vs write/exec commands
    (`e`, `g`, `w`) marked **bench-only / risky**; on hardware, an EXP records a
    successful `FW>` prompt and one verified memory read (e.g. a known string or
    vector) — until then the task stays open with the procedure marked
    **UNVERIFIED**.
  - Claims: C-2010–C-2019
  - Result: EXP-2026-11-06-M6.12-debug-console.md (`226bc4a`); `docs/research/clarion-debug-console.md` documents the Clarion MONI/FW> debug-console access procedure and safe memory-read workflow. Hardware verification (FW> prompt + verified memory read) remains **UNVERIFIED** per EXP/bench constraint.

---

- [x] **M8.A1 — Build env** `tools/qemu-ze0/build.sh`: pinned QEMU (≥ 8.2),
  patch, `--target-list=sh4-softmmu`. Done when `qemu-system-sh4 -M ze0`
  lists the machine. Status: done · Owner: session-ZMxuBT · Depends: —. Claims:
  C-1230–C-1239

- [x] **M8.A4 — CPU control block** (CCN/MMU from `hw/sh4/sh7750.c`: `PTEH`,
  `PTEL`, `TTB`, `TEA`, `MMUCR`, `CCR`, `EXPEVT`, `INTEVT`, `TRA`, TLB
  arrays). Done when the kernel-page call to VA `0x5b90` no longer faults.
  Depends: —. Claims: C-1260–C-1269
  Status: done · Owner: session-ZMxuBT. Result: `m8a4-0001..0003` factor
  the CCN/MMU into `sh4-ccn`; applies to 8.2.7, builds, instantiates; runtime
  UNVERIFIED (EXP-2026-11-06-M8.A4-cpu-control).

- [x] **M8.A5 — Boot-blocker stubs** (`0xffe70000` block with `+0x808` =
  `0xc0000000`, CPG `0xffc80000`, `0xfff80000`, UBC `0xff200000`, area 6
  `0x19300000`). Done when the unpatched kernel reaches the patched probe's
  point. Depends: —. Claims: C-1270–C-1279
  Status: done · Owner: session-ZMxuBT. Result: `ze0-stubs` device patch
  applies to 8.2.7, compiles, qtest-checked; kernel boot UNVERIFIED
  (EXP-2026-11-06-M8.A5-boot-stubs).

- [x] **M8.A7 — Trace tooling** `tools/qemu-ze0/run.sh` (logs, gdbstub,
  `summarize_log`, gdb script printing thread list + current module).
  Depends: —. Claims: C-1290–C-1299
  Status: done · Owner: session-ZMxuBT. Result: `run.sh` (machine select,
  log+summary, timeout, dry-run) and `gdb-ze0.py` (PC->module, 30 checks);
  stand-in QEMU only (EXP-2026-11-06-M8.A7-trace-tooling).

- [x] **M8.B4 — Boot arguments** at phys `0x08000020`–`0x0800002b`. Static
  read of nk is enough to start. Depends: — (M1.7 helps).
  - Status: done · Owner: task/m8.b4-boot-args-r2 · Critical: no
  - Claims: C-1340–C-1349
  - Result: EXP-2026-11-08-M8.B4-boot-args-r2 (C-1340–C-1346). Static read of nk.exe B/C (IMG256 `92aa525d…`) shows P2 `0xa8000020`–`0xa800002b` consumed diagnostically by AERTRACE dump `0x8804cc42` (B) / `0x8804c896` (C) with UTF-16LE `Navi Version : %c%c%c%c%c%c%c%c-%c%c%c\r\n` (`0x8800e5a8`), 11 bytes displayed (+0x00..+0x07,+0x09..+0x0b; +0x08 unread), no selector branch. Factory values IPL-set/unknown (C-535/706); M8 should seed deterministic placeholder (recommend `'-'` at +0x08).

- [x] **M9.3 — Bind the stub table to real VAs**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: — (M1.6b for automatic binding)
  - Goal: `stubs.py` (14 modeled, 3 planned) keyed by `COREDLL` export
    name/ordinal (`cerom.py exports coredll.dll`, C-527); model `sprintf`
    (ordinal 719), file I/O over a virtual FS, heap, critical sections,
    registry from JSON.
  - Done when: a selftest calls each stub through the dispatcher and an
    unknown export stops with `missing stub: NAME`.
  - Result: 24 stubs keyed by `module!export`/ordinal, dispatcher with virtual FS,
    heap, critical sections, registry and `sprintf`; unknown exports stop with
    `missing stub: NAME` (EXP-2026-11-06-M9.3-stub-bind).
  - Claims: C-1650–C-1659

- [x] **M9.4 — Engine interface with two back ends**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: `tools/l3_harness/engine.py`: `map`, `read/write mem`,
    `set_regs`, `call(va, args)`, `on_exec(va, handler)`; back ends Ghidra
    P-code (`EmulatorHelper`) and QEMU `-M none` + gdbstub.
  - Done when: both run a synthetic SH-4 snippet (add, loop, call to a stub)
    with identical results.
  - Result: `l3_harness/engine.py` (PySh4 reference, Ghidra/QEMU adapters);
    snippet parity proven, real engines SKIP (EXP-2026-11-06-M9.4-engine).
  - Claims: C-1660–C-1669

- [x] **M9.7 — Corpora** (`hddinfo_variants.py` 89, `ind_mutate.py` 8,
  `DRSTR` and tile mutations) in `tools/l3_harness/corpus.py`, each with
  the Python reader's verdict. Depends: —. Done when `manifest.py build`
  consumes them. Claims: C-1690–C-1699. Done: `l3_harness/corpus.py`
  builds 108 entries (EXP-2026-11-06-M9.7-corpus).

- [x] **M9.8 — `l3check.py`** (L3 rung of the verification ladder). Depends:
  M9.5, M9.7. Status: done · Owner: session-ZMxuBT. Result:
  `tools/l3check.py` runs every target (1 PASS, 5 BLOCKED), exit 3 when
  nothing is runnable (EXP-2026-11-06-M9.8-l3check). Claims: C-1700–C-1709

- [x] **M9.9 — Keep `l3-ghidra.md` "How to use L3" current.** Done with each
  M9 PR (no separate claim needed). Status: done · Owner: session-ZMxuBT.
  Done: current commands, statuses, targets
  and the seven-step reader procedure (EXP-2026-11-06-M9.9-l3-docs).

- [x] **M9.22 — Explain the `B30R048R` rebuild assertion (untrusted L2 pin)**
  - Status: done · Owner: claude/m9.22-input-region · Critical: yes
  - Depends: —
  - Goal: H14 ran the five pinned tiles: four and `LEV3456R` reproduce,
    `B30R048R` raises on an opaque record in the harness's background rebuild.
    Until that is explained, the tile's byte-identical claim and the L2 golden
    for it must not be trusted.
  - Precheck: `cd tools/ze0-viewer && python3 harness.py verify B30R048R`
    reproduces the raise (H14's transcript).
  - Scope: `tools/ze0-viewer/tools_ze0` (rebuild path) and that one tile; no
    format change.
  - Done when: the record and the failing invariant are named, the harness
    either round-trips the tile or refuses it with a clear message, and the L2
    pin is re-set or marked "known non-round-tripping" in the EXP.
  - Stop: if the tile is genuinely non-canonical, document it and stop —
    do not weaken the check.
  - Claims: C-2630–C-2639
  - Result: EXP-2026-11-08-M9.22-b30r048r-rebuild (C-2630–C-2639). The three refused records are named (dir `0x2ad00`, slots 6/8/11, k 1); the L2 pin is re-set in the EXP (tile round-trip and semantic digest pass, golden unchanged); `tools/ze0-viewer/bg_refused.py --selftest` OK (7 checks). Follow-up: M9.23.

- [x] **M9.23 — Model the three refused records of `B30R048R` (layer table past `geo_len`)**
  - Status: done · Owner: task/m9.23-b30r048r-opaque · Critical: no
  - Depends: M9.22 (done)
  - Goal: M9.22 found three level-1 background records (dir `0x2ad00`, slots
    6/8/11) whose layer table has entries past the header's geometry region
    (`geo_len 26`), so `parse_record` refuses them and the writer keeps them
    verbatim. Decide whether those entries are layers, shared data or padding.
  - Precheck: `cd tools/ze0-viewer && python3 bg_refused.py --selftest` (exit 0).
  - Scope: the bounded layer-table read in `tools_ze0/clarion_bg.py` (through
    `ze0-tools.patch`, audited by `setup.sh`), that one tile.
  - Done when: `parse_record` accepts the three records with the bounded region,
    `build_record` rebuilds them with `strict=True`, `harness.py verify` reports
    parse refused 0 on B30R048R with the control tiles unchanged, and the
    B30R048R L2 golden is re-set or unchanged with a stated reason.
  - Stop: if the entries past the region are not layers in any reader, document
    them as opaque in the EXP and stop; do not weaken the check.
  - Claims: C-2860–C-2869 (next free block; C-2630–C-2639 kept by M9.22, H23)
  - Unblock: none.
  - Result: EXP-2026-11-08-M9.23-b30r048r-opaque (C-2860–C-2866). The "entries
    past `geo_len`" are names-section bytes (`w11 = geo_off + geo_len`), not
    layers; `clarion_bg.parse_record` now bounds the table scan to `geo_len`.
    `parse_record` accepts and `build_record` rebuilds the 3 records
    byte-identically with `strict=True` (`bg_refused.py --selftest` 8 checks OK).
    `harness.py verify B30R048R` reports `parse refused 0`, `background rebuild
    ok 2958 (opaque 62)`, round-trip OK; controls B28R070R/B30R060R/B58R070R
    unchanged. L2 golden unchanged (tile bytes/semantic 16684 unchanged).

- [x] **M9.25 — `harness.py info` / viewer crash on opaque records**
  - Status: done · Owner: task/m9.25-harness-opaque-crash · Critical: no
  - Depends: M9.22 (done)
  - Goal: M5.4 noted `harness.py info` crashes on opaque records; M9.22 added
    `bg_refused.py` to *explain* the B30R048R refusals, but the viewer/harness
    path still needs to degrade gracefully on opaque records instead of
    crashing.
  - Precheck: reproduce the crash on `B30R048R.DAT` with `harness.py info` (or
    the command M5.4 named) and record the traceback text.
  - Scope: `tools/ze0-viewer/harness.py` (and its use of `tools_ze0`) error
    handling; no change to the vendored parser semantics except through the
    audited patch path if unavoidable.
  - Done when: `harness.py info` (and the affected subcommand) reports opaque
    records and exits 0 (or a documented non-crash code) on B30R048R, with the
    control tiles unchanged and `harness.py --selftest`/verify still passing.
  - Stop: if fixing it requires changing `tools_ze0` semantics, file that as a
    separate audited-patch task and stop.
  - Claims: C-2690–C-2699
  - Result: EXP-2026-11-08-M9.25-harness-opaque-crash. `harness.py info`
    classifies unreadable zlib/record failures and reports `, unreadable N`
    (exits 0). Precheck reproduced on M5.4-named factory B48R058R
    (`zlib.error` at `cmd_info:96`, 80 unreadable); B30R048R info exits 0 with
    unchanged census; controls B28R070R/B30R060R/B58R070R and B30R048R still
    pass `harness.py verify`; `bg_refused.py --selftest` OK.

