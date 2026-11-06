# TODO

The task board for parallel work. About 15 agents take tasks from this file
at the same time, so every task is self-contained: it says what to do, what
to start from, when it is done, what it waits for, and who owns it.

- Unknowns: [`docs/research/open-questions.md`](docs/research/open-questions.md).
- Evidence status of every claim: [`docs/research/claims.md`](docs/research/claims.md).
- The previous backlog (Gates 0–7, P0–P10, Steps 1–3) is frozen in
  [`docs/research/todo-history-2026-11-05.md`](docs/research/todo-history-2026-11-05.md).
  Its open items were moved here or listed under [Retired leads](#retired-leads).

**Goal:** a Leaf ZE0 map SD card built from OpenStreetMap (first
Dolnośląskie, then Poland, then Europe) that the unit accepts, displays and
routes on.

**Strategy (2026-11-05): go wide.** Work runs on nine fronts at once
(workstreams below). No front waits for another unless a task names an
explicit dependency. Each front always keeps at least two tasks in state
`open` with all dependencies done; when you close a task and see that your
front has fewer, add the next tasks (see rule 9).

## How to take a task

1. **Pick.** Choose a task with `Status: open` whose `Depends` are all done
   (`[x]` in this file or merged on `main`). Prefer tasks marked
   `Critical: yes`, then the front with the fewest active owners.
2. **Check for a claim.** A task is taken if its `Owner` is set, or an open PR
   has the task ID in its title (`[M2.1] …`). Look at both before starting.
3. **First commit: mark the task `in progress`.** Within your first 10
   minutes create a branch and make a commit that changes **only** your
   task's line to `Status: in progress · Owner: <branch>` (subject
   `todo: start <ID>`). **Push it at once** (`git push -u origin
   <branch>`), before any other work: an unpushed in-progress commit is
   invisible to the other agents and claims nothing. Then open a **draft PR** titled
   `[ID] short title`. The draft PR makes the claim visible before it
   merges. If two PRs claim the same ID, the lower PR number wins; the other
   agent closes its PR and picks another task.
4. **One task per PR, small PRs.** Touch only the files your task names, your
   own EXP record(s), your claim rows, and your task block in `TODO.md`.
   Do not reformat, reorder or "fix up" other tasks or other people's text.
   A finding outside your task becomes a new task (rule 9), not an edit.
5. **Rebase on `main` before you mark the PR ready**, and again if `main`
   moved while it waits. In `TODO.md`, `claims.md` and index tables keep
   both sides of a conflict; never drop another task's lines.
6. **Last commit: the work plus `done`.** Commit the actual work, and in the
   same commit set `Status: done`, tick `[x]` and add one line `Result:`
   naming the EXP (subject in the normal style, e.g. `tools: …`). Run `python3 tools/selftest.py` (and the task's
   own check) and paste the result into the PR body. Mark the PR ready.
   **Then merge it to `main` yourself** (merge the PR, or rebase on
   `origin/main` and `git push origin HEAD:main`; on a rejected push rebase
   and retry, never force-push `main`). A task is done only when its commits
   are on `origin/main`. **Afterwards delete your branch** (remote and local)
   and close any leftover draft PR.
7. **Blocked or negative.** If the done-when cannot be reached, set
   `Status: blocked`, write the exact blocker in one line, record the
   negative result as an EXP (method, scope, positive control), and add the
   follow-up tasks it suggests. A negative with a control is a result.
   Merge it to `main` and clean up the branch as in rule 6.
8. **Stale claims.** A claim with no push for 24 h may be released by the
   coordinator (`Status: open`, `Owner: —`). Push work in progress often.
9. **New tasks.** Add them at the end of the right workstream with the next
   free ID of that stream, the full field set, and `Owner: —`. Take the next
   free claim block from [ID allocation](#id-allocation).
10. **Methodology and data rules** in `AGENTS.md` apply to every task: start
    from `tools/cerom.py` for any firmware address (never fitted deltas),
    tools go in `tools/` with a synthetic self-test, observation and
    interpretation stay apart, and **vendor bytes never enter the repo**
    (only offsets, counts, hashes, short header bytes).
11. **Run on the real image before you close.** A firmware or format task is
    not `done` on synthetic data alone, and "no image in the checkout" is not
    a blocker: `IMG256` downloads in about a minute (see Shared inputs).
    Run your tool on it and put the real counts in the EXP. EXP-2026-11-06-H5
    found two tools that pass their self-test but match nothing on real bytes,
    and one blocker that the image itself answers.
12. **Network.** Only `files.viaaq.eu` (and package registries) are reachable
    from the Claude cloud sandbox; OSM hosts fail there (C-1716). Tasks that
    need such a host carry **`Runner: non-Claude`** in their status line:
    they are open and meant for agents outside that sandbox (with normal
    internet access). Claude sandbox agents skip them. Such a task records
    the download URL, date and SHA-256 of what it fetched, and never commits
    OSM extracts.

### ID allocation

Parallel agents collided on `EXP-…-48` and on several claim IDs (C-520,
C-521, C-528…C-533 were proposed twice). From now on:

- **EXP records:** `docs/experiments/EXP-YYYY-MM-DD-<TASK>-<slug>.md`, for
  example `EXP-2026-11-06-M1.2a-comp-header.md`. A second record for the
  same task adds `-2`, `-3`. The task ID makes the name unique because each
  task has one owner. Old numbered records keep their names.
- **Claim IDs:** every task below has a reserved block of ten (`Claims:
  C-600–C-609`). Use only your block. If you need more, or you add a new
  task, take the next free block: the highest block in this file plus ten.
- **Tool names:** a new tool states its file name in the task (`Input`
  or `Done when`); if two tasks would create the same file, the later one
  depends on the earlier.

### Task fields

```text
- [ ] **ID — title**
  - Status: open | in progress | blocked | done · Owner: — | <branch> · Critical: yes | no [· Runner: non-Claude]
  - Depends: — | IDs
  - Goal: one sentence.
  - Input: files, offsets, tools, samples.
  - Done when: a check that can fail.
  - Claims: C-xxx–C-xxx
```

### Shared inputs

| Name | How to get it | SHA-256 |
| --- | --- | --- |
| `IMG256` (firmware: A, B, C) | `curl -r 0-268435455 -o head256.img https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| `IMG` (full EU 2011 card, 7.5 GB) | same URL without `-r`; resume with `curl -C -` | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| `ROOT` (extracted map tree) | `python3 tools/verify.py --image IMG` (extracts to `archive/work/`) | — |
| Other years/markets | `https://files.viaaq.eu/maps/`, `docs/research/image-versions.md` | record per EXP |

CE images inside the card image: **A** (apps, `Navi.exe`) `--image-start
0x200200` (copy at `0x2000200`), **B** (kernel + updaters) `0x3e00200` (copy
at `0x4800200`), **C** (kernel + test mode) `0x5200200`. Tools for SH-4 code
in the cloud environment: `apt-get install binutils-sh4-linux-gnu
qemu-system-misc gdb-multiarch`.

## Priorities (product review 2026-11-06, second pass)

**Where we are against the goal.** Knowledge of the card *format* is
broad: most files decode and round-trip, one-tile edits pass L2, and the
coordinate tool exists. What is still missing is the other half of the goal,
the *unit's acceptance*: we cannot yet say why the firmware accepts or
rejects a card, and no tool builds a card image. Of the 11 tasks in draft
PRs right now, 9 are non-critical format/reader widening; **none of the
critical acceptance or compiler tasks has an owner.** Breadth stays the
strategy, but agents should take the list below first.

**Take these first (critical, ready, unowned), in this order:**

1. **M1.9** cross-image import names: one task that turns every `#1145` into
   `_wfopen` for all later firmware reading (M2.x, M3.x). Cheapest
   multiplier on the board.
2. **M2.13** SD unlock password and **M2.12** `HDD_CHK.ATT` attestation:
   the two card-identity gates. Without the password no clone or generated
   card can be read by the unit, whatever its content.
3. **M2.1 → M2.3**, then **M2.2 → M2.5**: the `HDD_INFO` parser and the
   map-code comparator (why a card is accepted).
4. **M5.10** card image builder (new): there is no tool that turns a card
   tree into a FAT32 image. M6.5 (first device test) cannot start without it,
   so it is now on the critical path.
5. **M5.1** OSM ingest (reopened: marked done without a tool) and
   **M4.15 → M4.16** (`RDSTM` framing and placement): the compiler front.
6. **M1.6c** thunks fix, then **M9.3 → M9.5**: run real firmware functions
   (M9.4 engine and M9.7 corpus are done).
7. **M1.2b** (XPRESS LZ77) / **M1.2d** / **M1.2c**: compression, which gates
   M1.3/M1.4, the registry (M2.7, M8.E2) and the compressed parts of
   `TestMode.exe` and `MapUpdate.exe`.

**Next milestone (definition of done for this phase):** an offline "S1
no-op card": `IMG256`-checked firmware facts say which files and identity
checks matter (M2.3, M2.12, M2.13), and `tools/mkcard.py` (M5.10) rebuilds
the factory card tree into an image that L1 + L2 + `realcheck.py` accept.
That is exactly what M6.5 needs on the bench, and it is reachable without
hardware.

**Process notes.** Rule 11 again: M4.8 and M5.1 were marked done with their
done-when unmet (M4.8 has no real-POI check, M5.1 has no `osm_ingest.py`);
both are corrected below. Draft PR #25 (`[M3.5]`) is left over after the
merge and was closed.

## Review 2026-11-06 (what changed since PR #11)

Merged since the last board update: M1.2a, M1.2b (tool), M1.6b (tool), M1.8,
M2.9, M2.10, M4.1, M4.5, M4.6, M4.13, M5.8, H2, LZNT1. Checked against
`IMG256` in EXP-2026-11-06-H5:

- **M2.1 was not blocked.** `coredll.dll` is in kernel image B, and its export
  table names every ordinal: `fn 0x004e7b8c` calls `_wfopen`, `fgetws`,
  `wcschr`, `wcsncpy`, `memset`, `fclose` (C-1710). It reads `HDD_INFO.TXT`
  line by line, so it is also the parser M2.3 needs (C-1711). M2.1 is open
  again with the names in its input.
- **Compression:** the M1.2a header model holds for 187 of 245 sections; the
  other 58 look like a second form with flag `0x10000000 | psize` (C-1712,
  C-1713 → M1.2d). On the real `NaviMapCC.dll` sections, lzss, lzx, lznt1 and
  xpress-huffman give no match at offsets 0…40; plain XPRESS LZ77 is the one
  untested candidate (C-1715 → M1.2b reopened).
- **`cerom.py thunks` finds no stub on the real image** (C-1714 → M1.6c);
  `sh4xref.py` does. M1.6b stays done as a tool, its real coverage is 0 %.
- **Data side:** `RDSTM001` rows decode and round-trip, meanings unproven
  (M4.1 → M4.15, M4.16); `MMAIN001.DAT` is a FAT root-directory log, not a
  manifest, and contradicts `drstr.md` at `0x18c`/`0x1ac` (M4.5 → H6, M3.8);
  names are ISO-8859-2 with all Polish letters present, collation and length
  limits unknown (M4.13 → M3.9, M4.18); `tile_diff.py` and the vendored
  `tools_ze0` make one-tile edits measurable (M5.8 → M5.9).
- **OSM is unreachable from the sandbox** (C-1716): M4.2 and the region run of
  M5.1 (now M5.1b) wait for `download.geofabrik.de` to be allowed or an
  extract on `files.viaaq.eu`; they are marked `Runner: non-Claude` (rule
  12). M4.17 attacks link attributes without OSM.
- **Stale claims released:** PR #8 (`[M2.1]`, superseded). M1.7 is claimed by
  PR #15.

## State after EXP-35…51 (what changed)

- **The address model is solved.** `tools/cerom.py` parses `ROMHDR`, the
  module TOC, `e32`/`o32` and `FILESentry` for A, B and C (EXP-35, -36),
  with `exports`, `memmap`/`ghidra` (EXP-48) and a synthetic self-test
  (EXP-47). `imports` is in PR #5 (EXP-50, M1.6). Every old delta-based
  address is suspect until re-derived through `cerom.py`.
- **The old map-code chain was in the wrong module.** `0x6fab2c` →
  `0x6faeb0` → `0x6fb05c` and `0x0369d400` (`sprintf` thunk) are `BT_MGR.dll`
  code (C-520, C-528). The real `HDD_INFO.TXT` / `SD Import` literals are in
  `Navi.exe` (C-521): VA `0x004e7d28` (paths), `0x004e8584` / `0x004e995c`
  (comparator messages).
- **First reader entry is anchored.** `Navi.exe` calls
  `OBJDLL!MAL_DataVol_getOffset` at `0x003778b2` and `0x00377b46`, `getSize`
  at `0x003778bc` and `0x00377b52`, through thunks `0x003d1bb0` / `0x003d1ba4`
  (EXP-50).
- **Compression is the one firmware unknown.** Code is never compressed
  (C-530); RW data sections and some `FILESentry` payloads are. zlib, LZMA
  and bz2 fail from the stream start (EXP-49, EXP-51); `tools/cecompress.py` has LZSS/LZX candidates tested
  on synthetic streams only (EXP-52). The streams share a
  header (see M1.2a).
- **Full-system emulation is possible, not hopeless.** Stock QEMU
  `-M none -cpu sh7785` runs B's `nk.exe` into the scheduler (EXP-37). This
  supersedes the old "L5: full-system QEMU is not realistic" verdict.
- **B carries the updater set** (`UpdateMng.exe`, `MapUpdate.exe`,
  `PRGUpdate.exe`, …) and C carries `TestMode.exe` (C-526): new, direct
  sources for how the unit checks and installs map data.
- **Data-side tools landed:** `hddinfo.py` (EXP-41), `section4.py` (EXP-42),
  `rdstm_schema.py` (EXP-43), IMF v1 + `imf_check.py` (EXP-44),
  `profile_validate.py` + `build.py --dry-run` (EXP-45), `diff_years.py`
  (EXP-46), `header_block.py` (EXP-40), `tools/l3_harness/` (EXP-38).

## Workstreams at a glance

| Stream | Front | Ready now (no open deps) |
| --- | --- | --- |
| H | Housekeeping: ledger, docs, tool overlap | H8 |
| M1 | Firmware tooling (decompression, disassembly, xrefs) | **M1.9, M1.6c, M1.2b**, M1.2c, M1.2d |
| M2 | Map code, activation, updater, error screens | **M2.1, M2.2, M2.12, M2.13b** (M2.7 in PR; M2.13, M2.11 done) |
| M3 | Reader contract (what the unit reads from the card) | **M3.1**, M3.6, M3.10 (M3.7, M3.8, M3.9 in PR) |
| M4 | Data formats (no firmware needed) | **M4.15**, M4.3, M4.8b, M4.12 (M4.7, M4.9, M4.10, M4.11, M4.18 in PR) |
| M5 | OSM compiler vertical slice (Dolnośląskie) | **M5.1, M5.10**, M5.9; M5.1b after M5.1 (non-Claude runner) |
| M6 | Hardware and safety (planning now, tests later) | M6.9 (non-Claude runner); tests need hardware |
| M8 | Full-system emulation (QEMU `ze0`) | M8.A1, M8.A2, M8.A4, M8.A5, M8.E1 (after M1.2c) |
| M9 | L3 toolkit (run firmware functions on our data) | **M9.3**, M9.1, M9.8 after M9.5 (M9.4, M9.7 done) |

**Critical path to a first accepted card:** M2.1 → M2.3 + M2.2 → M2.5 (why
a card is accepted; M1.8 done, ordinals named) · M2.12 (attestation) + M2.13
(SD unlock password) — the two card-identity checks M2.6/M2.8 surfaced ·
M3.1 → M3.2 (what is read) ·
M1.2b/M1.2c/M1.2d → M1.3 (initialised data for L3) · M1.6c/M1.9 → M9.2 →
M9.5 → M2.4 / M3.3 (checks against the real code) · M4.15 → M4.16 →
M4.2/M4.17 → M5.3 → M5.4 → M5.6 · M5.1 → M5.1b (non-Claude runner) · M5.10
(card image builder) → hardware M6.5–M6.7. Every other task
widens knowledge or tooling in parallel and is equally welcome.

---

## H — Housekeeping

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

- [ ] **H8 — Fix what H6 reported: `mmain.py`, `setup.sh`, two doc sentences**
  - Status: open · Owner: — · Critical: no
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
  - Claims: C-1890–C-1899

---

## M1 — Firmware tooling

Done: M1.1 (synthetic self-test, EXP-47), M1.5 (`cerom.py memmap`/`ghidra`,
EXP-48; the real Ghidra open is M9.2), M1.6 (`cerom.py imports`, EXP-50,
PR #5). Tool half of M1.2b: `tools/cecompress.py` (4 KiB LZSS and LZX
stored blocks, verbatim/aligned refused; synthetic only, EXP-52, C-570).

- [x] **M1.2a — Parse the compressed-section header**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: know where the compressed payload starts and how long it is.
  - Input: EXP-49 bytes. Section 1 (`NaviMapCC.dll` rva `0x13000`, psize
    `0x2c6`, vsize `0x5b8`) starts `84 04 00 | c6 02 00 | 10 00 00 00 |
    84 04 00 00 | b0 02 00 00 | 84 04 00 00 | 5b 80 …`; section 2 (psize
    `0x68c`, vsize `0xcc0`) starts `c0 0c 00 | 8c 06 00 | 10 00 00 00 |
    c0 0c 00 00 | 76 06 00 00 | c0 0c 00 00 | …`. Hypothesis to test: a
    22-byte header (`0x2c6 − 0x2b0 = 0x68c − 0x676 = 22`), a 24-bit
    uncompressed and compressed length, then per-block records
    (uncompressed size, compressed size); `0x484` would be the real data
    length of section 1 with the rest of vsize zero-filled. All 245
    compressed sections via `cerom.py sections`.
  - Done when: `cerom.py comphdr MODULE|--all` prints the parsed header for
    every compressed section and the hypothesis holds (or is refuted) on all
    245, with a count of exceptions; a synthetic self-test pins the parser.
  - Result: `cerom.py comphdr`; both recorded prefixes HOLDS, 0 exceptions;
    243 sections unmeasured (EXP-2026-11-05-M1.2a-comphdr, C-640/C-641).
  - Claims: C-640–C-649

- [ ] **M1.2b — Try the public CE / Microsoft LZ formats after the header**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M1.2a done: payload after the 22-byte header)
  - Goal: find a public decoder whose output length matches.
  - Input: the two EXP-49 sections; `tools/cecompress.py` (LZSS + LZX
    stored blocks already implemented and self-tested, EXP-52: run it on the
    real sections first, at the M1.2a payload offset); further candidates: Xpress "plain LZ77" and
    "LZ77+Huffman" and LZNT1 ([MS-XCA], open spec), LZX, and the CE
    romimage/`CECompress` formats as described by public ROM tools (cite the
    source in `docs/research/sources.md`; link, do not copy incompatible
    code).
  - Done when: one decoder gives exactly the expected length (`0x484` or
    `vsize`) and plausible content (pointers into `0x8c…`/module VAs,
    strings), or an EXP lists every decoder × offset tried with a positive
    control (each decoder round-trips its own test vector).
  - Old blocker resolved: the full payloads are in `IMG256` (file
    `0x01580ce0` len `0x2c6`, `0x015aca7c` len `0x68c`; extract with `dd`, see
    EXP-2026-11-06-H5). Real run so far: lzss, lzx, lznt1, xpress-huffman give
    0 matches at offsets 0…40 (C-1715). **Next step:** implement the XPRESS
    plain-LZ77 match decode ([MS-XCA] 2.3/2.4) with the spec's vector as
    control, rerun `probe`, then try per-block decoding using the M1.2a block
    records (`84 04 00 00 | b0 02 00 00 | …`: the stream may be framed in
    blocks rather than one run). Tool so far: EXP-2026-11-05-M1.2b, C-650.
  - Claims: C-650–C-659

- [ ] **M1.2c — Find the ROM decompressor in `nk.exe` and port it**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M1.8 helps)
  - Goal: read the kernel's own decompression routine instead of guessing.
  - Input: image B `nk.exe` (`cerom.py --image-start 0x3e00200 IMG sections
    nk.exe`), the loader path that tests `o32_flags & 0x2000`
    (`IMAGE_SCN_COMPRESSED`) and copies `o32` data to RAM; the kernel's
    `ulCopyEntries` handling; `sh4-linux-gnu-objdump -b binary -m sh4
    --adjust-vma=VA`.
  - Done when: the decompressor's VA and prototype are recorded, and either
    a Python port (`tools/cedecomp.py`, synthetic self-test) decodes the two
    EXP-49 sections to the M1.2a lengths, or its VA is handed to M8.E1 as a
    call target.
  - Claims: C-660–C-669

- [ ] **M1.3 — `cerom.py decompress` on all 245 sections**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M1.4 — Extract compressed `FILESentry` payloads**
  - Tool: `cerom.py files --extract --decompress` writes stored bytes,
    classifies OK/UNSUPPORTED/FAIL and never writes a wrong-length decode
    (EXP-55, C-573); EXP-51 says the real payload is not a stdlib format.
  - Status: open · Owner: — · Critical: no
  - Depends: M1.2b or M1.2c
  - Goal: read `boot.hv`, `default.hv`, `user.hv`, `ceconfig.h`,
    `initobj.dat`, `UpdateNK.skn`.
  - Input: EXP-51 (first `u16` equals the real size for three small files;
    `boot.hv` has a step-`0x4a` table); `cerom.py --image-start 0x3e00200
    IMG files`; image C has the same names with other sizes.
  - Done when: `cerom.py extract-file NAME` writes payloads whose length is
    `real` and `ceconfig.h` is readable text (do not commit it; quote ≤ 3
    lines in the EXP).
  - Claims: C-680–C-689

- [x] **M1.6b — Resolve all import thunks of all modules**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: M1.6 (PR #5)
  - Goal: a VA → `module!export` label table for every thunk, for Ghidra and
    for call-site search.
  - Input: EXP-50 stub pattern (`mov.l @(disp,PC),R0; mov.l @R0,R0; jmp @R0;
    nop`), `cerom.py imports` and `exports`.
  - Done when: `cerom_thunks.py` (or `cerom.py thunks`) `[MODULE|--all] --json` lists stub VA, slot
    VA and name for every A and B module; ≥ 95 % of `Navi.exe`'s 846 slots
    have a stub (report the rest); self-test on a synthetic stub.
  - Result: `cerom.py thunks` resolves 4/3/2-insn stubs through the OFT and
    export tables with coverage and `--min-coverage`; synthetic only, the
    real 846-slot run stays UNKNOWN (EXP-2026-11-05-M1.6b, C-690).
  - Claims: C-690–C-699

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

- [ ] **M1.2d — The second compressed-section header form (58 sections)**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: `comphdr` parses all 245 sections, so M1.3 knows every payload.
  - Input: `cerom.py --image-start 0x200200 IMG256 comphdr --all` (58
    REFUTED rows, e.g. `InfoBarCC.dll/sec2`, `Vehicle.exe/sec1`/`sec2`);
    hypothesis C-1713: flag word `0x10000000 | psize`, perhaps a multi-block
    or stored form.
  - Done when: `comphdr` recognises the second form (synthetic self-test for
    it) and reports `245 HOLDS` or lists the exceptions with their bytes;
    the EXP says whether form 2 is multi-block, stored, or another codec.
  - Claims: C-1740–C-1749

- [ ] **M1.6c — Make `cerom.py thunks` work on the real image**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: thunk labels for Ghidra (M9.2) and stubs (M9.3) from real bytes.
  - Input: C-1714 (`thunks Navi.exe` and `--all`: "no import stub matched");
    EXP-50 thunks `0x003d1bb0` (`getOffset`) and `0x003d1ba4` (`getSize`);
    `sh4xref.py`, which resolves them; `imports Navi.exe` (846 slots from
    `0x0055d000`); also `cerom.py va2file 0x003d1bb0` prints `0x-8c50f250`
    (module-relative VAs are not mapped — fix or document).
  - Done when: `thunks Navi.exe --min-coverage 95` exits 0 on `IMG256` and
    labels both EXP-50 thunks correctly; the cause of the miss is in the EXP
    and a self-test case reproduces it.
  - Claims: C-1750–C-1759

- [ ] **M1.9 — Cross-image import names (A → B's `coredll.dll`)**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: every import of every A module named, not just numbered.
  - Input: `cerom.py --image-start 0x3e00200 IMG256 exports coredll.dll`
    (1651 names, C-527, C-1710); `imports` of A modules; other B/C
    exporters (`commondll.dll`, `SYS_INF.dll`, `Errlogdll`, `CEDDK.dll`).
  - Done when: `cerom.py imports MODULE --resolve-with 0x3e00200` (or a
    `--names FILE` JSON) prints `COREDLL!_wfopen` instead of `#1145` for all
    846 `Navi.exe` slots, unresolved ones listed; `sh4xref.py --calls` uses
    the names; synthetic self-test.
  - Claims: C-1760–C-1769

---

## M2 — Map code, activation, updater

- [ ] **M2.1 — `Navi.exe` function that opens `HDD_INFO.TXT`**
  - Status: open · Owner: — · Critical: yes
  - Partial: EXP-2026-11-05-M2.1-hddinfo-fn (fn `0x004e7b8c`; callers only
    via pool `0x004dd1e4` in `fn 0x004dd028`). The blocker was wrong
    (C-1710): the ordinals are `memset` (1047), `_wfopen` (1145), `fgetws`
    (1143), `wcschr` (59), `wcsncpy` (66), `fclose` (1118), from image B's
    `coredll.dll`. Left: the arguments, the buffer it fills (destination of
    `wcsncpy`, size of `memset`), the `fgetws` line buffer size.
  - Depends: — (M1.8 helps)
  - Goal: name the function, its arguments and callers.
  - Input: literals at `Navi.exe` VA `0x004e7d28` / `0x004e7d2c` (C-521);
    `cerom.py --image-start 0x200200 IMG sections Navi.exe`; `imports`
    (CreateFile/ReadFile ordinals of `COREDLL`).
  - Done when: the EXP gives the function VA, the file API calls it makes,
    the buffer it fills (base register, offsets, lengths), and its callers
    (VA list).
  - Claims: C-720–C-729

- [ ] **M2.2 — The `SD Import: … is different` comparator**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M2.1 helps)
  - Goal: which fields are compared, against what, and with which checks.
  - Input: literals at `Navi.exe` `0x004e8584` / `0x004e995c`; the
    `Sys[0x%x]` vs `SD[0x%x]` formats; `tools/hddinfo.py` model M0.
  - Done when: each compared field is traced to a struct offset and a
    source (card vs system copy), and the `0 < userdata_type < 6` check is
    confirmed or refuted in this module.
  - Claims: C-730–C-739

- [ ] **M2.3 — `HDD_INFO.TXT` text → fields**
  - Status: open · Owner: — · Critical: yes
  - Depends: M2.1
  - Goal: the line order, separators and the six-line mapping.
  - Input: the M2.1 function `0x004e7b8c` itself (C-1711: `fgetws` loop,
    `wcschr` split, `wcsncpy` copy) and the buffer M2.1 names;
    `tools/hddinfo.py`. Can start now on the `fgetws` loop; M2.1 gives the
    struct base.
  - Done when: a `line → field → type → struct offset` table is in
    `docs/format/validation.md` and `hddinfo.py` follows it (self-test
    updated).
  - Claims: C-740–C-749

- [ ] **M2.4 — Predict accept/reject for the 89 `HDD_INFO` variants**
  - Status: open · Owner: — · Critical: yes
  - Depends: M2.2, M2.3, M9.5
  - Goal: run the real parser + comparator on `tools/hddinfo_variants.py`.
  - Input: L3 runner (M9.5), corpus (M9.7).
  - Done when: each variant has a firmware verdict and it is compared with
    `hddinfo.py classify`.
  - Claims: C-750–C-759

- [ ] **M2.5 — Source of `DIFFERENT MAP CODE`**
  - Status: open · Owner: — · Critical: yes
  - Depends: M2.2 (M2.9 helps)
  - Goal: which input decides the message: line 1, the `0x06000000` copy,
    or a NAND/system record.
  - Input: the message string (M2.9), M2.2 comparator.
  - Done when: the deciding input is named with the code path VA.
  - Claims: C-760–C-769

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

- [ ] **M2.12 — `HDD_CHK.ATT` CRC16 attestation (`SilentAuthenticate`)**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M1.9 helps)
  - Goal: know whether the unit requires a CRC16 attestation file on the card,
    and how it is computed, because a generated card must reproduce or satisfy
    it.
  - Input: `MapUpdate.exe` `SilentAuthenticate` `0x0001c210` and
    `CApi_MakeCRC16` (EXP-2026-11-06-M2.6, `docs/format/firmware.md`
    "MapUpdate.exe"); search `HDD_CHK.ATT` (ASCII and UTF-16) across A/B/C
    with a positive control; `sh4xref.py --calls`.
  - Done when: the EXP states which modules read `HDD_CHK.ATT`, the CRC16
    polynomial/seed and the byte range it covers, and whether `Navi.exe`
    (not just the updater) checks it at boot; `docs/format/validation.md`
    updated.
  - Claims: C-1870–C-1879

- [x] **M2.13 — The SD unlock PIN (firmware half found)**
  - Status: done · Owner: claude/project-thread-euxe0q · Critical: yes
  - Depends: — (M1.9 helps)
  - Result: EXP-2026-11-06-M2.13-sd-password. The owner's `SD PIN` service
    screen showed the full unlock PIN; its 12-char tail is a hardcoded
    `ProductTestData`/`SecurityCheck` literal in `PRGUpdate.exe` (VA
    `0x12498`) and `TestMode.exe` (VA `0x157f8`) — verified in `IMG256`
    (sha256 `249e0da5…`, plaintext not committed). The 8-digit prefix is
    runtime-generated (not a literal). The unit unlocked with it
    (`Unlocking. OK`), so the value is behaviourally confirmed.
  - Open (→ M2.13b): the ≤16-byte CMD42 form (the display is 20 chars > the
    SD 16-byte limit), the prefix derivation, and the `SDHC_SecurityUnLock`
    xref (its code is `COMPRESSED`, needs M1.2).
  - Claims: C-1880–C-1889

- [x] **M2.13b — The CMD42 byte form and the runtime prefix**
  - Status: done · Owner: claude/project-thread-9ynrai · Critical: yes
  - Depends: M2.13 (M1.2b/c for the `SDHC.dll` xref; M1.9 for names)
  - Goal: turn the known PIN into the exact ≤16-byte password a cloned card
    must carry, and name where the 8-digit prefix comes from.
  - Input: EXP-2026-11-06-M2.13 (literal VAs, the 20-vs-16 problem);
    `PRGUpdate.exe` around VA `0x12498` and its `CApi_GetModelCode` import
    (C-526); `SDHC.dll` `SDHC_SecurityUnLock` `0x039b2498` once decompressed;
    `byPasswordLen` logging (EXP-M2.8).
  - Lead (EXP-M2.13): the PIN is almost certainly 16 bytes = 4 unit bytes
    (the 8 hex digits of the displayed prefix) + the 12-byte ASCII literal,
    matching C-075. Confirm the 4 bytes = hex of the prefix.
  - Done when: the EXP confirms the 16-byte form, names the source of the 4
    unit-specific bytes (serial/model, with a code path), and states whether
    an independently locked card (not re-locked by the same unit) is feasible.
  - Result: 16-byte form and IOCTL→CMD42 flag map verified in `SDHC.dll`
    (`.text` is uncompressed); boot password from `nk.exe` HAL IOCTL
    `0x01013008` (copy from `0x89e439b8+0x100`, PROD shadow hypothesis);
    independent locking feasible (EXP-2026-11-06-M2.13b-sdhc-cmd42).
  - Claims: C-1950–C-1959 (moved: C-1940–C-1949 is M6.11, taken first)

---

## M3 — Reader contract

- [ ] **M3.1 — The `.ind` wrapper above `MAL_DataVol_getOffset`**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M1.6 done in PR #5)
  - Goal: name the `Navi.exe` function(s) around the four known call sites.
  - Input: call sites `0x003778b2`, `0x003778bc`, `0x00377b46`, `0x00377b52`
    (EXP-50); `OBJDLL.dll` exports `MAL_*`/`OBJ_*`.
  - Done when: the enclosing function VAs, their arguments and their callers
    are recorded, with what is done with offset/size.
  - Claims: C-820–C-829

- [ ] **M3.2 — `.ind` handling: `chunk_size` and seek vs scan**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.1
  - Goal: answer from code whether `chunk_size` sizes a buffer or is
    compared against `0x10000`, and whether the reader seeks by offset or
    scans for `78 9c`.
  - Input: M3.1 functions; `docs/format/cmp-ind.md`; `tools/ind_mutate.py`.
  - Done when: both answers are in `cmp-ind.md` with VAs.
  - Claims: C-830–C-839

- [ ] **M3.3 — Run the `.ind` reader on the 8 `ind_mutate.py` variants**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.2, M9.5
  - Done when: accept/reject per variant is recorded and compared with
    `cmpind.py`.
  - Claims: C-840–C-849

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
- [x] **M3.5 — Tile reader entry and the level table**
  - Status: done · Owner: task/m3.5-tile-reader-final · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: find the `MESH_ID`/`DIVID` code and confirm the six-level table
    (`VTb Tp;Lv;…`).
  - Input: `NaviMapCC.dll` strings and exports; `docs/format/map-tiles.md`.
  - Done when: the reader VA and the level-table layout are recorded in
    `map-tiles.md`.
  - Claims: C-860–C-869
  - Result: EXP-2026-11-06-M3.5-tile-reader (reader VAs 0x0041f26c/0x004259bc/0x0042757a in Navi.exe; six-level table `VTb Tp;Lv;St;F#|L1..L6|Sz;Adr`; NaviMapCC.dll has no reader code)

- [ ] **M3.6 — Which tile sections the renderer reads**
  - Status: open · Owner: — · Critical: no
  - Depends: M3.5
  - Done when: each tile section has "read by VA" or "ignored" in
    `map-tiles.md` (section 4 especially).
  - Claims: C-870–C-879

- [x] **M3.7 — How the router reads `RDSTM001` / `REFER` road records**
  - Status: done · Owner: — · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: the record fields the router uses (graph tuples, speed, one-way,
    restrictions).
  - Input: route/guide modules in A (`cerom.py modules`), `RDSTM` strings,
    `docs/format/rdstm.md`.
  - Done when: a field list with VAs is in `rdstm.md`; it feeds M4.1–M4.3.
  - Claims: C-880–C-889
  - Result: EXP-2026-11-06-M3.7-router-rdstm (`RDSTM001` is the TMC location
    record: volume+`LCTBL001.DAT` under type `0x14e4`, twelve fields with
    getters/VAs, per-record field directory; routing is mesh-keyed and no
    speed/one-way/restriction accessor exists — M4.2 must not look here)

- [x] **M3.8 — Does the firmware read `MMAIN001.DAT`?**
  - Status: done · Owner: task/m3.8-mmain-read · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: decide whether M5.6 must regenerate `MMAIN001.DAT` (the 4 KiB
    database header, C-1720) or can copy it.
  - Input: string search for `MMAIN` (ASCII and UTF-16) in all A/B/C modules
    with a positive control (`HDD_INFO.TXT` must be found the same way);
    `sh4xref.py --to` on the hits.
  - Done when: the EXP lists every reference with module/VA and what the code
    checks (label, record count, cluster), or shows no reference with the
    control; `docs/format/` and M5.6 input updated.
  - Result: EXP-2026-11-06-M3.8-mmain-read — one ASCII literal in
    `Navi.exe` `0x0017adac` (fn `0x0041a438`), no B/C reference; the reader
    requires exactly `0x1000` bytes and checks no label/count; the file is
    big-endian on the card. `tools/ce_strfind.py` added.
  - Claims: C-1780–C-1789

- [ ] **M3.9 — Name length limits and collation in the firmware**
  - Status: open · Owner: — · Critical: no
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

- [ ] **M3.10 — Decode the `DRSTR001`/`CMP.LST` functions found by M3.4**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: find the checks the firmware applies to `DRSTR001.DAT` and
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

---

## M4 — Data formats (no firmware or hardware needed)

- [x] **M4.1 — `RDSTM001`: decode one record and one node/link tuple**
  - Status: done · Owner: task/m4.1-rdstm-record · Critical: yes
  - Result: EXP-2026-11-05-M4.1-rdstm-record (`tools/rdstm_record.py`; synthetic self-test OK; 10 real rows at 0x1000 round-trip; field meanings still HYPOTHESIS)
  - Depends: —
  - Input: `tools/rdstm_schema.py`, `tools/rdstm_scan.py`, `ROOT`,
    `docs/format/rdstm.md` (status table, ranked unknowns).
  - Done when: a decoder with a synthetic test exists and one real record
    round-trips byte-identically.
  - Claims: C-890–C-899

- [ ] **M4.2 — `RDSTM001`: link attributes (speed class, one-way, class)**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (needs OSM, rule 12)
  - Note: EXP-2026-11-05-M4.2-rdstm-link-attrs failed for lack of OSM access
    and of a row → coordinate mapping. M4.17 tries the same question without
    OSM.
  - Depends: M4.1, M4.16
  - Done when: attribute values correlate with ≥ 5 known roads (OSM tags)
    in an EXP table.
  - Claims: C-900–C-909

- [ ] **M4.3 — Turn restrictions and connectivity encoding**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M4.1 helps)
  - Done when: one known restriction (OSM `restriction=*` at a named
    junction) is found and decoded.
  - Claims: C-910–C-919

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

- [ ] **M4.7 — Rename path for names/addresses**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Input: `ADDRE`/`POINT`/`ZCODE`/`LCTBL` (`docs/format/refer.md`,
    `tools/mutate_refer_poi.py`, `tools/lctbl_names.py`).
  - Done when: a renamed POI with a different-length name passes L2.
  - Claims: C-950–C-959

- [x] **M4.8 — Coordinate transform tool**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Input: `tools/mesh_grid.py`, `docs/format/coord-zcode-icode.md`, the
    five target tiles, the 52742 vs 52736 longitude origin question.
  - Done when: `tools/coord.py` converts lat/lon ↔ mesh/0..2047 and ≥ 10
    known POIs land within a few metres.
  - Result: `tools/coord.py` converts lat/lon <-> cell/packed/local with both origins, 15 fixtures (EXP-2026-11-06-M4.8-coord); 10-POI image check open.
  - Claims: C-960–C-969

- [ ] **M4.8b — Check `coord.py` on 10 real POIs**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.8
  - Goal: the original M4.8 done-when, unmet at merge: prove the transform
    on real data before M5.2 splits OSM ways with it.
  - Input: `tools/coord.py`; `IMG` (full card, `ROOT` via `verify.py`);
    `POINT`/`ADDRE` records (`docs/format/refer.md`) for ≥ 10 named POIs whose
    position is known independently (well-known landmarks: town halls,
    railway stations; take coordinates from Wikipedia/Wikidata pages, not
    OSM, rule 12); EXP-M4.8 follow-ups (2x local scale, 52742 vs 52736 origin).
  - Done when: the EXP lists ≥ 10 POIs with decoded vs reference lat/lon and
    the error in metres, states which origin and local scale fit, and
    `coord.py` self-test pins the chosen constants.
  - Claims: C-1900–C-1909

- [ ] **M4.9 — `ADDRE` remaining grammar**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: 6-/12-byte index cells, `c0` vs `c8` grammar, subtypes
    `0x54`/`0x58`, `40 XX YY` point encoding, trailer table.
  - Done when: each item is decoded or `UNKNOWN` with a method in
    `refer.md`, with a test on a synthetic record.
  - Claims: C-970–C-979

- [ ] **M4.10 — POI icon code → `BICON001` PNG**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Done when: a mapping table for ≥ 20 POI categories is in
    `docs/format/assets.md` (icons are not committed).
  - Claims: C-980–C-989

- [ ] **M4.11 — `LEV3456R.DAT` coarse levels 3–5 semantics**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: what the overview levels contain and how to regenerate them from
    OSM (needed for zoomed-out display).
  - Done when: `map-tiles.md` describes levels 3–5 content and a rebuild of
    one level from decoded records is byte-identical.
  - Claims: C-990–C-999

- [ ] **M4.12 — `COORD001`/`ZCODE`/`ICODE001` remaining fields**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: `COORD001` `level`, the `ZCODE` offset base, `ICODE001` trie roots.
  - Done when: each is decoded with a test, in `coord-zcode-icode.md`.
  - Claims: C-1000–C-1009

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

- [ ] **M4.15 — `RDSTM001` framing and node reciprocity**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.1
  - Goal: prove the record size and the `src`/`dst` reading on the whole
    file, not 10 rows.
  - Input: `tools/rdstm_record.py`, `rdstm_schema.py`, `rdstm_scan.py`;
    `RDSTM001.DAT` from `IMG` (SHA-256 `f822044c…`, EXP-M4.1); the framing
    drift at `0x10a0`; rows below `0x1a700`; `docs/format/rdstm.md` ranked
    unknowns 1–3.
  - Done when: the EXP explains the drift (header, variable record, block
    boundary), gives the row count per region, and reports a reciprocity
    test (every `dst` appears as a `src`, or the share that does) against a
    shuffled-field control; `rdstm.md` updated.
  - Claims: C-1800–C-1809

- [ ] **M4.16 — Place `RDSTM001` rows on the map**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.15 (M4.8 helps)
  - Goal: a row → tile/mesh → coordinate link, which M4.2, M4.3 and M5.3 need.
  - Input: `ref`/`src`/`dst` values (M4.1), tile road records
    (`tools_ze0`, `harness.py`), `COORD001` mesh formula, `mesh_grid.py`.
  - Done when: ≥ 20 rows are matched to tile road segments with coordinates,
    with the join key named and a random-key control showing ~0 matches.
  - Claims: C-1810–C-1819

- [ ] **M4.17 — Link attributes without OSM: road numbers as ground truth**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.15
  - Goal: find the road-class field from roads whose class is known by their
    number (`A4`, `A18`, `S8`, `E40`, `DK94`… are motorways/expressways/
    national roads by definition).
  - Input: road-number strings in `LCTBL001` (`tools/name_strings.py`) and
    tile name sections; the RDSTM candidate fields (`code`, `tail`, `pad2`).
  - Done when: an EXP table maps ≥ 5 numbered roads of different classes to
    their record field values, with a control (unnumbered streets), or shows
    there is no link.
  - Claims: C-1820–C-1829

- [x] **M4.18 — `LCTBL001` record framing**
  - Status: done · Owner: task/m4.18-lctbl-framing · Critical: no
  - Depends: —
  - Goal: per-field name counts and lengths (M4.13 could only count per
    stream).
  - Input: the 517 zlib streams (`tools/name_strings.py`), NUL-separated
    pieces (1,329,518), `rdstm.md` notes on `LCTBL`, `tools/lctbl_names.py`.
  - Done when: the record layout inside a stream is decoded (or `UNKNOWN`
    with method), a parser round-trips one stream byte-identically, and the
    EXP gives counts and max length per field.
  - Claims: C-1830–C-1839
  - Result: EXP-2026-11-06-M4.18-lctbl-framing — 16-byte header + four
    even-padded name slots + opaque footer; 247,089 records, per-field
    non-empty/max 36,461/10, 66,189/85, 243,907/99, 109,944/64;
    `tools/lctbl_records.py` round-trips all 517 streams byte-identically and
    the 2014/2016 controls use the same layout.

---

## M5 — OSM compiler vertical slice (Dolnośląskie)

Done: M5.0 (IMF v1 + `tools/imf_check.py`, EXP-44). See
`docs/research/osm-vertical-slice.md` and `profiles/dolnoslaskie-test.*`.

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

- [ ] **M5.1b — Ingest the real Dolnośląskie extract**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (needs OSM, rule 12)
  - Input: `https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf`.
  - Depends: M5.1
  - Done when: IMF for the region passes `imf_check.py`; extract date,
    URL and SHA-256 recorded; counts of ways/nodes per `highway=*` in the EXP.
  - Claims: C-1840–C-1849

- [ ] **M5.2 — Mesh splitter**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.8, M5.1
  - Done when: every way is assigned to meshes and clipped at borders, and
    `imf_check.py --assign-tiles` agrees.
  - Claims: C-1040–C-1049

- [ ] **M5.3 — OSM → Clarion road class/speed table**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.2
  - Done when: a table covers every `highway=*` value in the region with
    unmapped values listed.
  - Claims: C-1050–C-1059

- [ ] **M5.4 — Tile writer: roads only**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.2 (M5.3 for classes)
  - Input: `tools/ze0-viewer/vendor/osm2clarion`, factory neighbours,
    `section4.py preserve`.
  - Done when: one generated tile passes L2.
  - Claims: C-1060–C-1069

- [ ] **M5.5 — Connectivity across tile borders**
  - Status: open · Owner: — · Critical: no
  - Depends: M5.4, M4.3
  - Claims: C-1070–C-1079

- [ ] **M5.6 — Rebuild `DRSTR001`/`MMAIN001`/`.ind`/`CMP.LST`**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.4, M4.5 (M3.8: a verbatim `MMAIN001` copy is enough for the
    mount; the firmware checks only the 4096-byte length — EXP-2026-11-06-M3.8)
  - Input: copy `MMAIN001.DAT` verbatim when the tile set is unchanged; if
    tiles change, regenerate the `0x1ac` totals (C-164, big-endian) with
    `tools_ze0/make_mmain.py`, because `cardcheck` enforces the sum even
    though the firmware read path does not. Keep the file big-endian (C-1788).
  - Done when: L1 passes on the output card tree.
  - Claims: C-1080–C-1089

- [ ] **M5.7 — Street names into the name sections**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.7, M5.4
  - Claims: C-1090–C-1099

- [x] **M5.8 — One-tile diff report**
  - Status: done · Owner: task/m5.8-tile-diff · Critical: no
  - Result: EXP-2026-11-05-M5.8-tile-diff (`tools/tile_diff.py`; factory vs mutate output: 148 bytes in 2 ranges; `tools_ze0` package committed as `tools/ze0-viewer/tools_ze0/`)

- [ ] **M5.9 — `tile_diff.py`: match moved streams and name the records**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: a generated tile's diff reads as "changed record X", not as
    remove + add at another offset.
  - Input: `tools/tile_diff.py` (offset-based matching), `tools_ze0`
    (`clarion_tile.py` section/record layout), `section4.py`.
  - Done when: on the M5.8 mutate output the report shows 1 changed stream
    (0 added/removed) and the level/record/vertex that changed; self-test
    covers a moved stream.
  - Claims: C-1850–C-1859

- [ ] **M5.10 — Card image builder (`tools/mkcard.py`)**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M2.13 for the lock state; M3.8 for `MMAIN001`)
  - Goal: turn a card tree into an SD image the unit could read: the missing
    link between every writer and the first bench test (M6.5, S0/S1 of
    `card-test-plan.md`).
  - Input: the factory layout from `IMG` (MBR, FAT32 partition 0, 64 KiB
    clusters, label `QSD-309-101`, root order incl. `MMAIN001.DAT` in
    cluster 2, the `0x06000000` copy that `cardcheck.py --image` checks);
    `cardcheck.py`, `l2check.py`, `realcheck.py`; firmware partitions are
    copied verbatim from the source image, never committed.
  - Done when: `tools/mkcard.py --from-image IMG --tree ROOT -o out.img`
    rebuilds the map partition from an unchanged tree and the result is
    byte-identical to `IMG` (or every differing byte range is listed and
    explained: timestamps, free-cluster order); `cardcheck.py --image out.img`
    passes; synthetic self-test on a small FAT32 image; the EXP says what the
    tool cannot reproduce (SD lock state, CID).
  - Claims: C-1910–C-1919
  - Depends: —
  - Goal: an automatic report of what changed vs what was preserved between
    a factory and a generated/mutated tile (sections, records, bytes).
  - Input: `harness.py compare-tiles`, `section4.py`.
  - Done when: `tools/tile_diff.py A B --json` works on a factory tile and
    on the `harness.py mutate` output.
  - Claims: C-1100–C-1109

---

## M6 — Hardware and safety

No hardware is available now. Planning tasks are open; tests wait.

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

- [ ] **M6.9 — Set and verify an SD lock password from a PC**
  - Status: open · Owner: — · Critical: no · **Runner: non-Claude** (needs a
    physical SD host; Marek or a local agent)
  - Depends: — (M2.13 for the real password)
  - Goal: know that we can put a card into the lock state the unit expects
    (C-798) before buying bench hardware.
  - Note (EXP-2026-11-06-M2.13): the unit has its own SD LOCK/UNLOCK menu, so
    a card used in that same unit can be (un)locked by the unit — a PC CMD42
    station is only needed to lock a card the unit has not seen, or to verify
    the lock state off-bench. Scope M6.9 to that off-bench verification.
  - Input: EXP-2026-11-06-M2.8 (CMD42 lock/unlock, `SD UNLOCK NG`),
    EXP-2026-11-06-M2.13; `mmc-utils` / Linux `mmc` sysfs on a native SDHCI
    slot (USB readers do not pass CMD42); a spare card. Host without
    SDHCI: the RP2040 tool of M6.11, `docs/hardware/sd-blocker-pico.md` §7.1.
  - Done when: `docs/research/card-test-plan.md` has a tested procedure to
    set, check and clear a CMD42 password on a spare card from Linux, with
    the reader model that worked; or the EXP shows which host hardware is
    needed.
  - Claims: C-1920–C-1929
- [ ] **M6.11 — RP2040 (Raspberry Pi Pico) SD lock/unlock tool**
  - Status: blocked · Owner: claude/project-thread-9ynrai · Critical: no
  - Blocker: `.uf2` not built; the Claude sandbox refused building the external Pico SDK, so the build runs locally (doc §6) as the first step of M6.9.
  - Depends: — (M2.13 for the real password; M6.9 runs the bench test)
  - Goal: a cheap SPI-mode CMD42 host, so M6.9 does not depend on finding a
    native SDHCI slot (USB readers do not pass CMD42).
  - Input: EXP-2026-11-06-M2.8 (C-790–C-799), C-075; SD Physical Layer
    Simplified Spec (CMD42, CMD13 R2, SPI data tokens).
  - Done when: `docs/hardware/sd-blocker-pico.md` gives parts, wiring,
    build, flash and operator steps; `tools/sdlock-pico/` builds a `.uf2`
    with the Pico SDK; its host self-test proves no frame can carry ERASE;
    no password literal is committed.
  - Result (partial): hardware doc + firmware + host self-test (572 checks,
    ERASE unreachable, 3 mutants caught); `.uf2` not built, see Blocker
    (EXP-2026-11-06-M6.11-pico-sdlock).
  - Claims: C-1940–C-1949
- [ ] **M6.10** Unit NAND/PROD backup procedure before any bench test (from
  EXP-2026-11-06-M6.4). Status: blocked (hardware). Claims: C-1930–C-1939
- [ ] **M6.2** Owner's US 2011 SD dump (read-only, SHA-256). Status: blocked
  (hardware) · Owner: Marek. Claims: C-1140–C-1149
- [ ] **M6.5** First on-device test with the no-op clone. Status: blocked
  (hardware; Depends M6.3). Claims: C-1150–C-1159
- [ ] **M6.6** First on-device test with one changed tile. Status: blocked
  (Depends M6.5, M5.6). Claims: C-1160–C-1169
- [ ] **M6.7** Routing test across the changed tile. Status: blocked
  (Depends M6.6). Claims: C-1170–C-1179

---

## M7 — Scale and release (later)

- [ ] **M7.1** Full Dolnośląskie run, size budget. Depends M5.6. Claims:
  C-1180–C-1189
- [ ] **M7.2** All-Poland road network. Depends M7.1. Claims: C-1190–C-1199
- [ ] **M7.3** Europe motorway/trunk network. Depends M7.2. Claims:
  C-1200–C-1209
- [ ] **M7.4** Profiles schema v2 migration and the writer behind
  `tools/build.py` (validator and `--dry-run` exist, C-564–C-567). Status:
  open · Depends: —. Done when the three profiles validate as v2 and
  `build.py` calls M5 stages. Claims: C-1210–C-1219
- [ ] **M7.5** User guide and risk statement; "research only" until M6.7.
  Depends M6.7. Claims: C-1220–C-1229

---

## M8 — Full-system emulation (QEMU `ze0` machine)

Background: [`docs/research/full-system-emulation.md`](docs/research/full-system-emulation.md),
EXP-37. Stages: **F0** boot log → **F1** stable kernel → **F2** drivers →
**F3** SD mounted → **F4** `Navi.exe` headless → **F5** screen. Rules: QEMU
code lives in `tools/qemu-ze0/` as an out-of-tree patch with no vendor bytes;
each register model cites the nk/driver code it was read from (VA via
`cerom.py`); each stage ends with an EXP. Time box F0+F1: one week from the
first M8.A claim; F2+ only after M8.D1.

**Ownership rule for M8:** M8.A1 creates `tools/qemu-ze0/build.sh` and the
patch layout; M8.A2…A7 may start in parallel against stock QEMU 8.2 with
`-M none` (as `ce_qemu_probe.py` does) and rebase onto M8.A1 when it lands.

- [ ] **M8.A1 — Build env** `tools/qemu-ze0/build.sh`: pinned QEMU (≥ 8.2),
  patch, `--target-list=sh4-softmmu`. Done when `qemu-system-sh4 -M ze0`
  lists the machine. Status: open · Owner: — · Depends: —. Claims:
  C-1230–C-1239
- [ ] **M8.A2 — Machine skeleton** `hw/sh4/ze0.c`: `sh7785`, RAM at phys
  `0x08000000` (128 MiB), P1/P2 aliases, unimplemented-device catch-all
  over `0xff800000`–`0xffffffff` and areas 4/6. Done when
  `ce_qemu_probe.py`'s access list is reproduced with `-M ze0`. Status:
  open · Depends: — (M8.A1 to merge). Claims: C-1240–C-1249
- [ ] **M8.A3 — Built-in loader** (`kernel=0x3e00200`, `app=0x200200`):
  parse `ECEC`/`ROMHDR`, copy B/C and A to `physfirst & 0x1fffffff`, PC =
  `nk.exe` entry. Done when booting needs no `-device loader`. Status: open
  · Depends: M8.A2. Claims: C-1250–C-1259
- [ ] **M8.A4 — CPU control block** (CCN/MMU from `hw/sh4/sh7750.c`: `PTEH`,
  `PTEL`, `TTB`, `TEA`, `MMUCR`, `CCR`, `EXPEVT`, `INTEVT`, `TRA`, TLB
  arrays). Done when the kernel-page call to VA `0x5b90` no longer faults.
  Status: open · Depends: —. Claims: C-1260–C-1269
- [ ] **M8.A5 — Boot-blocker stubs** (`0xffe70000` block with `+0x808` =
  `0xc0000000`, CPG `0xffc80000`, `0xfff80000`, UBC `0xff200000`, area 6
  `0x19300000`). Done when the unpatched kernel reaches the patched probe's
  point. Status: open · Depends: —. Claims: C-1270–C-1279
- [ ] **M8.A6 — Debug serial** (`sh_serial` at `0xffe46000`; writer
  `0x8804cfa4`, pointer at `0x8804ce78`). Done when the CE boot banner
  appears or an EXP shows why not. Status: open · Depends: M8.A2. Claims:
  C-1280–C-1289
- [ ] **M8.A7 — Trace tooling** `tools/qemu-ze0/run.sh` (logs, gdbstub,
  `summarize_log`, gdb script printing thread list + current module).
  Status: open · Depends: —. Claims: C-1290–C-1299
- [ ] **M8.A8 — F0 EXP + register table** in `docs/format/firmware.md`.
  Depends: M8.A3…A6. Claims: C-1300–C-1309
- [ ] **M8.B1 — INTC model** (`0xff802000…`, `0xff804000…`, from
  `OEMInterrupt*` and the ISR at `VBR+0x600`). Done when a TMU0 interrupt is
  delivered and acknowledged. Depends: M8.A2. Claims: C-1310–C-1319
- [ ] **M8.B2 — TMU** (`0xffd80000`, `0xffd81000`, `hw/timer/sh_timer.c`).
  Done when `CurMSec` advances. Depends: M8.B1. Claims: C-1320–C-1329
- [ ] **M8.B3 — RTC/time** (`OEMGetRealTime`). Depends: M8.A2. Claims:
  C-1330–C-1339
- [ ] **M8.B4 — Boot arguments** at phys `0x08000020`–`0x0800002b`. Static
  read of nk is enough to start. Depends: — (M1.7 helps). Claims:
  C-1340–C-1349
- [ ] **M8.B5 — Milestone F1**: `filesys.exe` and `device.exe` start, 60 s
  without a fault. Depends: M8.B1, M8.B2. Claims: C-1350–C-1359
- [ ] **M8.C — one task per peripheral** (C1…C22, table in
  [`todo-history-2026-11-05.md`](docs/research/todo-history-2026-11-05.md),
  section M8.C). Each: read the driver init, decide stub / model / HLE,
  done when its init returns without hanging boot. Static reading of a
  driver's init can start now (Depends: —); the model waits for M8.B5.
  Claim one row at a time as `[M8.C10]` etc.; claim block: C-1360 +
  10 × row number (C1 → C-1370–C-1379, …, C22 → C-1580–C-1589). Priority
  rows: **C10 SD host**, C4 micon/power, C8 NOR flash, C18 display.
- [ ] **M8.D1 / M8.D2 — Decision gates** after F1 and F3 (see history
  file). Owner: coordinator with Marek. Claims: C-1590–C-1599
- [ ] **M8.E1 — Run the kernel's ROM decompressor as a tool**
  - Status: open · Owner: — · Critical: yes
  - Depends: M1.2c (decompressor VA). Does **not** need F1: call the
    function directly under `-M none` + gdbstub with RAM-only state, like an
    L3 call.
  - Done when: the two EXP-49 sections decode to the M1.2a lengths, then
    all 245 sections and the `FILESentry` payloads (cross-check M1.3/M1.4).
  - Claims: C-1600–C-1609
- [ ] **M8.E2 — Registry as loaded** (`boot.hv`, `default.hv`, `user.hv`):
  driver list, `IoBase`, `Irq`, load order. Two routes: static hive parser
  after M1.4, or a RAM dump after M8.B5. Done when the driver table is in
  `firmware.md`. Depends: M1.4 or M8.B5. Claims: C-1610–C-1619
- [ ] **M8.E3 — Dump loaded process images** (`Navi.exe` + DLLs after init)
  for L3. Depends: F4. Claims: C-1620–C-1629

---

## M9 — L3 toolkit: run firmware functions against our data

Design: [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md). Code
lives in **`tools/l3_harness/`** (exists: `manifest.py`, `stubs.py`,
`rommap.py`, `runner.py` with `check`/`plan`; `run` is blocked). Pure-Python
parts are covered by `tools/l3_harness/selftest.py`.

- [ ] **M9.1 — Module map on the real image**
  - Status: open · Owner: — · Critical: no
  - Depends: — (tool done: `cerom.py memmap`, EXP-48)
  - Done when: `cerom.py memmap` on `IMG256` lists every A + B section,
    `rommap.py convert --skip-compressed` + `validate` pass, and counts per
    module are recorded in an EXP.
  - Claims: C-1630–C-1639
- [ ] **M9.2 — Ghidra project builder**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.1 (M1.6b for thunk labels)
  - Goal: `tools/l3_harness/ghidra_import.py` (pyghidra, headless): all
    A + B sections at their VAs, exports named, thunks labelled, SH-4
    calling convention.
  - Done when: Ghidra shows `OBJDLL!MAL_DataVol_getOffset` at the EXP-50
    call sites and the `HDD_INFO` string xref at `0x004e7d28` (this also
    closes the M1.5 Ghidra check).
  - Claims: C-1640–C-1649
- [ ] **M9.3 — Bind the stub table to real VAs**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M1.6b for automatic binding)
  - Goal: `stubs.py` (14 modeled, 3 planned) keyed by `COREDLL` export
    name/ordinal (`cerom.py exports coredll.dll`, C-527); model `sprintf`
    (ordinal 719), file I/O over a virtual FS, heap, critical sections,
    registry from JSON.
  - Done when: a selftest calls each stub through the dispatcher and an
    unknown export stops with `missing stub: NAME`.
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
- [ ] **M9.5 — Runner `run` end-to-end**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.2 or M9.4, M9.3
  - Goal: `runner.py run FUNC --input FILE [--engine ghidra|qemu] --json`
    with targets in `tools/l3_harness/targets.json`.
  - Done when: one target runs end-to-end and prints `accepted`, return
    value, stub log, digests.
  - Claims: C-1670–C-1679
- [ ] **M9.6 — First real target**: the decompressor (if M1.2 is still open
  when M9.5 lands) or the `HDD_INFO` comparator (M2.2). Depends: M9.5 and
  M1.2c or M2.2. Claims: C-1680–C-1689
- [x] **M9.7 — Corpora** (`hddinfo_variants.py` 89, `ind_mutate.py` 8,
  `DRSTR` and tile mutations) in `tools/l3_harness/corpus.py`, each with
  the Python reader's verdict. Depends: —. Done when `manifest.py build`
  consumes them. Claims: C-1690–C-1699. Done: `l3_harness/corpus.py`
  builds 108 entries (EXP-2026-11-06-M9.7-corpus).
- [ ] **M9.8 — `l3check.py`** (L3 rung of the verification ladder). Depends:
  M9.5, M9.7. Claims: C-1700–C-1709
- [ ] **M9.9 — Keep `l3-ghidra.md` "How to use L3" current.** Done with each
  M9 PR (no separate claim needed).

---

## Retired leads

Do not take these up again; each was superseded by the CE ROM TOC
(EXP-35/-36) or by a later experiment.

| Old item (history file) | Why retired | Replaced by |
| --- | --- | --- |
| Global VA / module-base / delta fitting (EXP-05…29, Gate 0a) | exact addresses come from `cerom.py` | M1.*, H4 |
| `HDD_INFO` chain `0x6fab2c` → `0x6faeb0` → `0x6fb05c`, data delta `0x02800000`, helpers `0x0369d400`/`0x036922cc`/`0x0367b180` | `BT_MGR.dll` code, `sprintf` thunk (C-520, C-528) | M2.1–M2.3 in `Navi.exe` |
| "Find the `0x2e0xxxx` module export table" | import-thunk area, not a module | M1.6, M1.6b |
| "Parse the `romimage` XIP section table" | done: `cerom.py` | — |
| "Re-resolve `0x0367–0x0369` and the map-module delta" | VA map is exact now; `0x0367b180` is BT_MGR (C-519) | — |
| "No XIP table" (C-380/C-381) | retracted | — |
| "Static is closed for the reader" (EXP-29) | made under the wrong address model | M3.1, M3.4, M3.5 |
| "Map filenames have zero literal references" | same; must be re-run with real VAs | M3.4 |
| L5 "full-system QEMU is not realistic" | `nk.exe` reaches the scheduler (EXP-37) | M8 |
| `tools/l3/` as the L3 location | the harness lives in `tools/l3_harness/` | M9 |
| Spare-card `HDD_INFO`/`.ind` matrices as next steps | no hardware; shrink them with M2.4/M3.3 first | M6.3 |
| `NaviStateCC` vtable hunts (EXP-27…29) | parked; COM objects come from runtime or `DllGetClassObject` with real VAs | M9 / M8.E3 if needed |
