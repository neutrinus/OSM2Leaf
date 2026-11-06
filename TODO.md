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

13. **Firmware confirms every format we write (Marek, 2026-11-06).** A file
    type we generate counts as *confirmed* only when its reader in the
    firmware is located (an M3 task, VAs in `docs/format/`) and as
    *accepted* only when an L3 target runs that reader on our generated file
    and gets the expected values (an M9 task). Round-trip tools and L2 are
    necessary, not sufficient. The live status of each file type is the
    matrix in [`docs/research/reader-coverage.md`](docs/research/reader-coverage.md)
    (H11); update its row in the same PR as your task.

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

## Priorities (product review 2026-11-06, fourth pass)

Earlier passes and the two older "what changed" sections are frozen in
[`docs/research/todo-history-2026-11-06.md`](docs/research/todo-history-2026-11-06.md).

**Nearest milestone: Marek's US unit shows a name we wrote.** The US path
(Marek, 2026-11-06) stays ahead of the OSM compiler because it tests the
real accept → display → route loop on the only hardware we have, with the
unit's own map code `QSD-301-103` (the region lock is the unit, M2.7).

| Stage (`card-test-plan.md`) | Card | Built by | Status |
| --- | --- | --- | --- |
| S0 factory clone | `LEAF_2011-2012_US.img` as is (`53342430…c5383`) | `dd` | ready for Marek now (**M6.2**) |
| S1 no-op recompression | `POINT010` page `0x840ba0` recompressed unchanged | **M5.13** | open |
| S2 POI rename | `HANA HEALTH CENTER` → `OSM2LEAF TEST POI1` (Hana, Maui, HI) | M5.12 done; image via **M5.13** | edit done, image must be rebuilt |
| S3 geometry | one road vertex moved in a US tile | **M5.14** | open |

**Why the M5.12 image must not go on the unit as is (PM check on the real
US image).** The factory US root directory starts with a volume-label entry
`QSD-301-103` (attr `0x08`, root slot 0; the BPB label is `NO NAME`).
`mkcard.py`'s fresh-build path (used for any changed tree) never writes that
entry, which is why M5.12's `cardcheck` warned "no volume label"; it also
re-lays out the whole FAT. That card would test three variables at once
(label, FAT layout, changed file). **M5.13** writes the changed file into its
existing cluster chain in a copy of the factory image, so S1/S2 differ from
S0 only in that file. **M5.12b** fixes `mkcard.py` for the compiler path.

**What the last round established (verified on the files, 2026-11-06):**

- **Acceptance gates are now mostly named.** `DIFFERENT MAP CODE` is decided
  in `AppLaunch.dll` (B/C) by an 11-byte compare of the unit's target-info
  record (`KernelIoControl 0x0101302C` +0x60) against the card's
  `VER_INFO/HDD_INFO.TXT`, *not* the `0x06000000` copy (M2.5).
  `HDD_CHK.ATT` (CRC-16/KERMIT) is read only by `MapUpdate.exe`, the updater,
  not by `Navi.exe` at boot (M2.12). The `SD Import … is different` messages
  validate user data (`*.slc`/`*.hlc`), not the map (M2.2). `HDD_INFO.TXT`
  line→field table is in `validation.md` (M2.3). Consequence: a US card that
  keeps `VER_INFO` untouched should pass the map-code gate on a US unit; for
  Poland we still need the exact 11 bytes and the `MAP DATA BASE UNMATCH`
  input (**M2.15**).
- **The compiler spine has tools, not yet a real tile.** `mesh_split.py`
  (M5.2), `tilewriter.py` (M5.4, synthetic 48/48), `mkcard.py` (M5.10,
  EU no-op rebuild byte-identical), `tile_diff.py` (M5.9). M5.4 was marked
  blocked on "no vendor tile" — that is not a blocker under rule 11; it is
  **open again** with a provisional class table until M5.3.
- **Compression is still unsolved:** 0/245 sections decode (M1.3); XPRESS
  LZ77 is ruled out too (M1.2b). Next: read the kernel's own routine
  (**M1.2c**) and try public CE ROM decoders (**M1.2e**, non-Claude).
- **The `.ind` reader was not where we looked.** `MAL_DataVol_*` are
  disc/data-volume fingerprint helpers (M3.1), `fn 0x00418748` only builds
  `.IND` paths (M3.2). New angle: find zlib's `inflate` and walk up (**M3.2b**).
- **`RDSTM001` 16-byte framing is refuted** (M4.15, 0/10 reciprocity) and no
  join key places rows on the map (M4.16) → M4.16b/c/d stay open.
- **L3 runner works end to end** on a probe (M9.5, PySh4 + stubs); the first
  real target should now be the map-code compare that M2.5 found (**M9.6**,
  re-scoped), which unblocks **M2.4**. Ghidra (M9.2) cannot be installed in
  the Claude sandbox → `Runner: non-Claude`.
- **US `DRSTR001` does not round-trip** (`l2check` diff at `0x1ae0`, also on
  the untouched factory tree, M5.12) → **M4.20**; M5.6 must write DRSTR for
  generated cards, so the model has to be right on both markets.

**Take these first (critical, ready, unowned), in this order:**

1. **M3.11 → M9.10** and **M3.2b → M9.11 → M9.12**: the software gate for
   the US rename. In parallel **M5.13** (in-place image patch → S1/S2
   images), **M5.12c** and **M3.12** (other copies of the name). M6.2 (S0)
   is optional now; the edited cards wait for the gate.
2. **M5.14** (US vertex move, S3); M4.8c (coord on the US grid) is done, so it is ready.
3. **M2.15** + **M9.6** → **M2.4**: the exact map-code bytes, run on the real
   comparator.
4. **M5.4** (real tile, provisional classes) → **M4.20** → **M5.6** →
   **M5.12b** → **M5.11**: the Dolnośląskie spine.
5. **M1.2c** (+ **M1.2e** non-Claude) → M1.3/M1.4/M8.E1: compression.
6. **M3.2b** → M3.2 → M3.3: the `.cmp`/`.ind` reader.

**Software before the car (Marek, 2026-11-06).** A car test is expensive,
so every edited card first passes the firmware's own code in L3:
**M3.11** (find the `POINT` reader) → **M9.10** (it returns
`OSM2LEAF TEST POI1`, software S2) and **M3.2b** → **M9.11** (the firmware's
`.cmp` layer reads our recompressed pair, software S1) → **M9.12**
(`l3check.py --card`, the gate). **M3.12** says whether the name search
holds a second copy. M6.5/M6.6 depend on these; only S0 (the factory
clone) may go into the car before them.

**Every generated format is confirmed by the firmware (Marek, 2026-11-06,
rule 13).** Three levels, cheapest first: (1) the reader is located and the
format doc cites its VAs (M3.5, M3.10, M3.11–M3.16); (2) an L3 target runs
that reader on our file (M9.10, M9.11, M9.13–M9.15) and the map-load chain
runs on a whole tree (M9.16, the "mock `Navi.exe`"); (3) full `Navi.exe` in
the emulated unit (M8 → F4 → M8.E4). **H11** keeps the per-file matrix;
nothing goes into the car before its rows reach level 2. **M5.15** wires it into one
command: factory image + OSM → card image → L1/L2/L3 checks (+ M8.E4 when
the emulator reaches F4).

**Phase-2 milestone (unchanged):** one OSM-generated Dolnośląskie tile on a
card image that passes L1 + L2 + `realcheck.py` and every known gate (M5.11).
The OSM inputs (M4.2, M5.1b) still need a non-Claude runner (rule 12).

**Needs Marek:** S0 on the unit (M6.2); building the Pico `.uf2` locally if
the unit's own SD LOCK menu is not used (M6.11); running the non-Claude
tasks (M1.2e, M4.2, M5.1b, M9.2) on a machine with normal internet.

## Workstreams at a glance

| Stream | Front | Ready now (no open deps) |
| --- | --- | --- |
| H | Housekeeping | **H11** (reader-coverage matrix) |
| M1 | Firmware tooling (decompression) | **M1.2c**, M1.2e (non-Claude) |
| M2 | Map code, activation, updater | **M2.15**, M2.16, M2.14 |
| M3 | Reader contract | **M3.11, M3.2b, M3.12, M3.13, M3.14, M3.15, M3.10**, M3.6, M3.16, M3.17 |
| M4 | Data formats | **M4.20, M4.16b**, M4.8b, M4.16c, M4.16d, M4.3, M4.12, M4.17; M4.2 non-Claude |
| M5 | Compiler + US edits | **M5.13, M5.12c, M5.4**, M5.12b; M5.14 after M5.13; M5.1b non-Claude |
| M6 | Hardware (Marek) | **M6.2 (S0)**; M6.5–M6.7 follow M5.13/M5.14 |
| M8 | Full-system emulation | M8.A1, M8.A2, M8.A4, M8.A5; M8.E1 after M1.2c |
| M9 | L3 toolkit | **M9.6, M9.13** (ready), M9.8; M9.10–M9.12, M9.14–M9.16 after their M3 readers; M9.2 non-Claude |

**Critical path to a first accepted card:**
· **US (nearest):** software gate M3.11 → M9.10, M3.2b → M9.11 → M9.12;
images M5.13; then car M6.2 S0 → M6.5 S1 → M6.6 S2 → (M5.14) M6.7 S3.
· **Poland (goal):** M5.1 → M5.2 → M5.4 → M4.20 + M5.6 → M5.12b → **M5.11**,
gated by M2.15 + M9.6/M2.4 (map code) and M5.3 ← M4.2 (road classes).
Supporting: M1.2c → M1.3/M8.E1 · M3.2b → M3.2 → M3.3 · M4.16b → M4.2/M5.3.

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

- [ ] **H11 — Reader-coverage matrix: one row per file type we generate**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: one page that shows, for every file the OSM compiler must write,
    how far we are from "the firmware reads it correctly" (rule 13).
  - Input: `docs/format/sd-card-layout.md` (top-level tree), `docs/format/*.md`,
    `claims.md`, `tools/l3_harness/targets.json`, the M3/M9/M8 tasks below.
    Rows at least: `MAPAL001` tiles (`B*R.DAT`), `LEV3456R.DAT`, `REFER001`
    `POINT*`, `ADDRE*`, `ZCODE*`, `ICODE001`, `COORD001`, `LCTBL001`,
    `INTER*`, `FRWAY*`, `INDEX003`, the `.cmp`/`.ind` container, `DRSTR001`,
    `CMP.LST`, `MMAIN001`, `VER_INFO/HDD_INFO.TXT`, `RDSTM001`, and the
    verbatim-copy set (`BICON001`, `OPNG`, `SPEECH`, `TMC`, `REFER002`).
  - Done when: `docs/research/reader-coverage.md` has the matrix with
    columns *generate or copy* · format doc · writer tool · offline
    round-trip (L1/L2) · firmware reader VA (M3 task) · L3 target (M9 task) ·
    L3 result · full-system result (M8 F4) — each cell a link, a task ID or
    `—`; every row whose reader or L3 target has no task gets one (next
    free IDs) in the same PR.
  - Claims: C-2170–C-2179

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

- [x] **M1.2b — Try the public CE / Microsoft LZ formats after the header**
  - Status: done · Owner: task/m1.2b-xpress-lz77 · Critical: yes
  - Result: EXP-2026-11-06-M1.2b-xpress-lz77 — implemented XPRESS plain LZ77 in tools/cecompress.py + tools/xpress.py (selftest green); real sections 1/2 give 0 matches in 115 attempts each (xpress-lz77 raises corrupt offset); codec still unknown.
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

- [x] **M1.2c — Find the ROM decompressor in `nk.exe` and port it**
  - Status: done · Owner: task/m1.2c-rom-decompressor · Critical: yes
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
  - Result: EXP-2026-11-06-M1.2c-rom-decompressor. nk.exe (B, `0x3e00200`)
    loader `fn 0x880385e4` tests `o32_flags & 0x2000` at `0x88038666` and calls
    `0x88037590(dataptr,psize,dest,vsize)`. Decompressor chain
    `0x88037590`→`0x88037464` (section framing, form 1/2 block loop)→`0x8803a384`
    (per-block CE LZXD-like, block type 4/E8). VAs+prototypes recorded;
    `tools/cedecomp.py` self-test ok but pure-Python block decode **not** ported
    (EXP-49 sections: 0 matches with cecompress) — **M8.E1 call target** handed
    off (`DECOMP_WRAP 0x88037590` / `DECOMP_SECT 0x88037464`).

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

- [x] **M1.2d — The second compressed-section header form (58 sections)**
  - Status: done · Owner: task/m1.2d-comphdr-form2 · Critical: yes
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
  - Result: `comphdr` parses 245/245 (187 form 1, 58 form 2 multi-block
    `[u24×n][0x10,0x1000,X,0x1000]+0x8d80805b`, `n-1` blocks, `u24[-1]==psize`;
    not stored), 0 exceptions; IMG256 245 HOLDS (EXP-2026-11-06-M1.2d-comphdr-form2,
    C-1740–C-1746). `realcheck` 8/8, `selftest` 34/0/19, `cerom --selftest` 411.

- [x] **M1.6c — Make `cerom.py thunks` work on the real image**
  - Status: done · Owner: task/m1.6c-thunks-real-image · Critical: yes
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
  - Result: EXP-2026-11-06-M1.6c-thunks-real-image.md; root cause fixed (module-local realaddr/slot VAs vs ROM `va2file`, R0-only 4-insn, inlined IAT call sites). IMG256 Navi.exe: 845/846 slots covered (99.9%), 3728 call-site records (100% resolved with `--resolve-with 0x3e00200`); EXP-50 `0x003d1bb0`→`OBJDLL!MAL_DataVol_getOffset#3`, `0x003d1ba4`→`OBJDLL!MAL_DataVol_getSize#4` (`--min-coverage 95` exits 0). `realcheck.py IMG256` 8/8 PASS (thunks pin updated), `selftest.py` 32/0/19.

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

- [ ] **M1.2e — Try public CE ROM decoders on the two EXP-49 sections**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (needs GitHub/source downloads, rule 12)
  - Depends: —
  - Goal: M1.2b/M1.3 rule out lzss, lzx, lznt1, xpress-huffman and plain XPRESS
    LZ77 (0/245). Before porting the kernel routine (M1.2c), test the decoders
    that public Windows CE ROM tools already carry.
  - Input: lead, unverified — Willem Hengeveld's `dumprom` / `eimgfs` (nlitsme on
    GitHub) and itsutils handle compressed CE ROM sections; the two EXP-49
    sections and the M1.2a/M1.2d header forms (`cerom.py comphdr`).
  - Done when: one decoder gives exactly the M1.2a lengths for both sections
    (then port it into `tools/cecompress.py` with licence and attribution checked
    and rerun M1.3), or the EXP lists each tool, version, URL, SHA-256 and the
    output it gave.
  - Claims: C-2070–C-2079

---

## M2 — Map code, activation, updater

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

- [x] **M2.3 — `HDD_INFO.TXT` text → fields**
  - Status: done · Owner: task/m2.3-hddinfo-fields · Critical: yes
  - Result: EXP-2026-11-06-M2.3-hddinfo-fields (tools/hddinfo.py FieldDef/HDD_INFO_FIELDS + field_layout; validation.md table; selftest 43 checks)
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
  - Status: blocked · Owner: task/m2.4-hddinfo-variants · Critical: yes
  - Blocker: firmware verdicts require the real L3 target (M9.6), unavailable offline; offline model-M0 gives 66 ACCEPT / 23 DIFFERENT. See EXP-2026-11-06-M2.4-hddinfo-variants.
  - Depends: M2.3, M9.6 (M2.15 for the offline model)
  - Goal: run the real parser + comparator on `tools/hddinfo_variants.py`.
  - Input: L3 runner (M9.5), corpus (M9.7). The map-code comparator is
    `AppLaunch.dll` `fn 0x03bd2ad8` (M2.5), not M2.2's user-data check.
  - Done when: each variant has a firmware verdict and it is compared with
    `hddinfo.py classify`.
  - Claims: C-750–C-759

- [x] **M2.5 — Source of `DIFFERENT MAP CODE`**
  - Status: done · Owner: task/m2.5-different-map-code · Critical: yes
  - Depends: M2.2 (M2.9 helps)
  - Goal: which input decides the message: line 1, the `0x06000000` copy,
    or a NAND/system record.
  - Input: the message string (M2.9), M2.2 comparator.
  - Done when: the deciding input is named with the code path VA.
  - Claims: C-760–C-769
  - Result: EXP-2026-11-06-M2.5-different-map-code (IMG256 `92aa525d…`). `DIFFERENT MAP CODE` = AppLaunch B dispatcher `0x03bcafb8` error code `0x50`, produced by router `fn 0x03bd2ecc` (B, `0x03bd2ed4/0x03bd2eda–0x03bd2ee2`; C mirror pools `0x03bb2c54`→`0x03bb2858`, `0x03bb2c64`→`0x03bb2a64`) when `fn 0x03bd2ad8` (B; C `0x03bb2858`) returns 0. Deciding input: **NAND/system kernel target-info** `KernelIoControl(0x0101302C)` output `+0x60` (11 bytes) vs **card `\SystemSD\VER_INFO\HDD_INFO.TXT` parsed line-1/`base_code`** (11 bytes), byte-for-byte (`0x03bd2c1e–0x03bd2c3e`); logs `VerInf:%s / HddInf:%s`. **Not** the `0x06000000` copy, **not** an HDD_INFO text record in NAND (C-766).

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

- [x] **M2.12 — `HDD_CHK.ATT` CRC16 attestation (`SilentAuthenticate`)**
  - Status: done · Owner: task/m2.12-hdd-chk-att · Critical: yes
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
  - Result: docs/experiments/EXP-2026-11-06-M2.12-hdd-chk-att.md (HDD_CHK.ATT UTF-16LE only in MapUpdate.exe/B; Navi.exe has no ref, HDD_INFO.TXT control found in A; `SilentAuthenticate` 0x0001c210 reads 0x80 bytes, decodes 20 hex chars from ctx+120 → 10 bytes, `CApi_MakeCRC16`/commondll 0x03c04214 = CRC-16/CCITT reflected/KERMIT seed 0 poly 0x8408 must yield 0, then `sub_0001e3f4` verifies 128 bytes; C-1870–C-1879; validation.md updated)

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

- [ ] **M2.14 — Unit NOR "EEPROM" area at `0x0000A000` (zelemar) vs our images**
  - Status: open · Owner: — · Critical: no
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
  - Claims: C-2000–C-2009

- [ ] **M2.15 — The exact `HDD_INFO` bytes behind `DIFFERENT MAP CODE` and `MAP DATA BASE UNMATCH`**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M2.5, M2.3 done)
  - Goal: for the Poland card we must know which `HDD_INFO.TXT` bytes the
    unit compares, and against what. M2.5 found the two launcher checks but
    left the parsed line/offset of the 11-byte compare and the `0x03bd2ce4`
    range check open.
  - Input: `AppLaunch.dll` B `fn 0x03bd2ad8` / C `0x03bb2858` (11-byte compare
    vs target-info `+0x60`), B `fn 0x03bd2ce4` / C `0x03bb2a64` (MapDBVer
    range, target-info `+112/+114`), the HDD_INFO parse state machine (`*r9`
    global `0x1f74b30`); EXP-2026-11-06-M2.5, `validation.md`, `hddinfo.py`.
  - Done when: `validation.md` names, for both checks, the HDD_INFO line,
    byte offset and length and the unit-side source, with VAs; `hddinfo.py
    classify` follows it (self-test pins one pass and one fail per check);
    the 89 M2.4 variants are re-classified with the new model.
  - Claims: C-2080–C-2089

- [ ] **M2.16 — `HDD_CHK.ATT` on real cards and `sub_0001e3f4`**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M2.12)
  - Goal: M2.12 shows `HDD_CHK.ATT` is read only by `MapUpdate.exe`; confirm
    whether factory cards carry it at all and close the layout question.
  - Input: EU and US images (Shared inputs); `MapUpdate.exe!SilentAuthenticate`
    (B `0x0001c210`), `sub_0001e3f4`, `ctx+120`.
  - Done when: the EXP says per image whether `HDD_CHK.ATT` exists (path,
    size, SHA-256 only) and `sub_0001e3f4` is decoded or explicitly deferred
    with what blocks it.
  - Claims: C-2090–C-2099

---

## M3 — Reader contract

- [x] **M3.1 — The `.ind` wrapper above `MAL_DataVol_getOffset`**
  - Status: done · Owner: task/m3.1-ind-wrapper · Critical: yes
  - Depends: — (M1.6 done in PR #5)
  - Goal: name the `Navi.exe` function(s) around the four known call sites.
  - Input: call sites `0x003778b2`, `0x003778bc`, `0x00377b46`, `0x00377b52`
    (EXP-50); `OBJDLL.dll` exports `MAL_*`/`OBJ_*`.
  - Done when: the enclosing function VAs, their arguments and their callers
    are recorded, with what is done with offset/size.
  - Result: EXP-2026-11-06-M3.1-ind-wrapper; `fn 0x00377870` (vols {3,4,7,8} fingerprint, `memcmp` on `*2`-scaled off/size, status `0x03f1`/`0x03f7`, caller `fn 0x00377ae0@0x377ce4`) and `fn 0x00377ae0` (vol 7 `getOffset/getSize`→`memcpy` from `0x01205040+off*2`, disc/version checks; caller none in uncompressed `.text`); OBJDLL `MAL_*` #1-#6; C-820–C-829.
  - Claims: C-820–C-829

- [ ] **M3.2 — `.ind` handling: `chunk_size` and seek vs scan**
  - Status: blocked · Owner: task/m3.2-ind-handling · Critical: yes
  - Blocker: `.ind` chunk reader (chunk_count/chunk_size/chunk_offset consumer) not identified; `fn 0x00418748` is a resolver only. See EXP-2026-11-06-M3.2-ind-handling.
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

- [x] **M3.10 — Decode the `DRSTR001`/`CMP.LST` functions found by M3.4**
  - Status: done · Owner: task/m3.10-drstr-cmplst-fns · Critical: no
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
  - Result: EXP-2026-11-06-M3.10-drstr-cmplst-fns (C-1860–C-1869). `0x0041ba90` (CMP.LST) does only `fopen`/`fclose` — no content read/compare (existence check). `0x00419684`→`sub_00419350` reads/parses DRSTR001 (heap `*0x009cfcdc` ≤`0x77220`, stack 40B) with size/read checks at `0x419388,0x4193da,0x4193e4,0x419462-0x419468,0x419496-0x4194a6` (`_modlu`/`>=200` caveat noted) but **no 0x2f root / 40-node / 324-entry compare found** (C-1864, strengthens C-859); `sub_004191d0` bounds `entry_count+1 < 15000` at `0x41920a`. All in `Navi.exe`, coredll ordinals named. `drstr.md` updated.

- [ ] **M3.2b — Find the `.cmp` chunk reader by walking up from `inflate`**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: M3.1/M3.2 show the `MAL_DataVol_*` and `.IND` string leads miss the
    reader. Every `.cmp` chunk is zlib, so the reader must call `inflate`.
  - Input: image A modules (`cerom.py sections`); zlib message strings
    (`incorrect header check`, `invalid distance too far back`,
    `invalid stored block lengths`), the zlib version string and the
    `inflate … Copyright` banner as anchors; `sh4xref.py --to`;
    `docs/format/cmp-ind.md`.
  - Done when: the module and VAs of `inflateInit2_`/`inflate`/`inflateEnd`
    are recorded, their callers are listed, and the caller that loops over
    `chunk_offset[]` is named (then answer M3.2's two questions); or the EXP
    shows, with a positive control, that zlib sits in a compressed section.
  - Claims: C-2060–C-2069

- [ ] **M3.11 — The `POINT` record reader in `Navi.exe`**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: the function that walks a decoded `POINT0xx` page (`tag,len2`
    records, `0x60`/`0x68`, record size `2*len2`) and copies a POI name out.
    It is the first target of the software check of the US rename (M9.10)
    and of every later POI edit.
  - Input: the 8-char volume id table at `0x00179338` (`POINT0`, C-881), the
    file-name builder `0x003fbed8`, the volume lookup `0x0040b358` and the
    descriptor switch at `0x004125a8` (C-880: `0x14e8` → `REFER001` +
    `INDEX003.DAT`); `docs/format/refer.md` (record framing, C-952/C-953);
    `sh4xref.py`, `cerom.py` on `IMG256`.
  - Done when: `firmware.md` names the record-walk function and the
    name-copy function with VAs, arguments (buffer, length, index or offset)
    and output (where the name lands), each tied to the record framing in
    `refer.md`; or the EXP lists every candidate examined with a positive
    control and the exact blocker.
  - Claims: C-2120–C-2129

- [ ] **M3.12 — `INDEX003.DAT`: is it the POI name search index?**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M5.12c overlaps: coordinate the scan)
  - Goal: know whether the unit finds a POI by name through a second copy
    of the name (then the S2 rename must update it too) or through pointers
    into the `POINT` pages.
  - Input: `REFER001/INDEX003.DAT` on the EU and US images (`cmpind.py
    extract` if it is a `.cmp` pair); C-880 (`0x14e8` resolves `REFER001` +
    `INDEX003.DAT`); M3.11 output.
  - Done when: `refer.md` describes the `INDEX003` record layout well enough
    to say, for the US POI `HANA HEALTH CENTER` (`POINT010`, page `0x840ba0`,
    record 0), which `INDEX003` entry refers to it and whether that entry
    holds name bytes; the EXP gives counts and offsets only.
  - Claims: C-2130–C-2139

- [ ] **M3.13 — The `ADDRE` (address) reader**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M3.11 shows the pattern for `REFER001` families)
  - Goal: confirm the `ADDRE` grammar (M4.9) against the code that reads it.
  - Input: id table `0x00179338` (`ADDRE0`), name builder `0x003fbed8`, lookup
    `0x0040b358`, descriptor switch `0x004125a8`; `refer.md`, EXP-2026-11-06-M4.9.
  - Done when: `refer.md` names the reader VA(s) and maps each grammar field
    (C-970–C-979) to the instruction that consumes it, or lists the fields
    the firmware never reads.
  - Claims: C-2180–C-2189

- [ ] **M3.14 — `ZCODE` / `ICODE001` / `COORD001` readers**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: the region/index/coordinate tables decide where a generated
    Poland map lives; confirm their layout (C-110, C-1992,
    `coord-zcode-icode.md`) from the code.
  - Input: id table `0x00179338` (`ZCODE0`), `coord-zcode-icode.md`, M4.8c, M4.12.
  - Done when: `coord-zcode-icode.md` gives the reader VA per file and which
    fields each one uses, with VAs.
  - Claims: C-2190–C-2199

- [ ] **M3.15 — The `LCTBL001` name-table reader**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M3.7 located the `LCTBL001.DAT` load at `0x004125a8`)
  - Goal: Polish street/place names go through this table (M4.18 framing,
    M3.9 collation); confirm framing and encoding from the code.
  - Done when: `refer.md` (or `rdstm.md`) names the record-walk and
    string-decode VAs and states the encoding the code assumes.
  - Claims: C-2200–C-2209

- [ ] **M3.16 — `INTER` / `FRWAY` readers**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M4.16c for the `ref` lead)
  - Done when: the reader VAs and consumed fields are in `refer.md`.
  - Claims: C-2210–C-2219

- [ ] **M3.17 — Which files can be copied verbatim to a Poland card**
  - Status: open · Owner: — · Critical: no
  - Depends: H11
  - Goal: decide, with evidence, which files we never generate
    (`BICON001`, `OPNG`, `SPEECH`, `TMC`, `REFER002`, `RDSTM001`) and whether
    any of them carries region-specific content that must be emptied or
    rebuilt for Poland (e.g. US EV POIs in `REFER002`, US TMC tables).
  - Done when: each file has *copy / empty / generate* in
    `reader-coverage.md` with the reason; any *generate* gets a task.
  - Claims: C-2220–C-2229

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

- [x] **M4.15 — `RDSTM001` framing and node reciprocity**
  - Status: done · Owner: task/m4.15-rdstm-framing · Critical: yes
  - Result: EXP-2026-11-06-M4.15-rdstm-framing — 16-byte rows from 0x1000 give 0/10 reciprocity; drift at 0x10a0; schema prefers 2-byte record (0.371). Negative on the 16-byte hypothesis.
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

- [x] **M4.16 — Place `RDSTM001` rows on the map** (blocked: no join key)
  - Status: blocked · Owner: task/m4.16-rdstm-placement · Critical: yes
  - Depends: M4.15 (M4.8 helps)
  - Goal: a row → tile/mesh → coordinate link, which M4.2, M4.3 and M5.3 need.
  - Input: `ref`/`src`/`dst` values (M4.1), tile road records
    (`tools_ze0`, `harness.py`), `COORD001` mesh formula, `mesh_grid.py`.
  - Blocker: M4.1 16-byte fields (`ref/src/dst/code`) give no segment-specific
    join (hits at chance vs dense lid space; `ref`∩parcel/AB=0; C-1810) and
    M4.15/M3.7 leave framing/TMC semantics undecoded. `INTER*` `ref` byte-pattern
    enrichment (real>>random) is an unverified lead (C-1811).
  - Result: EXP-2026-11-06-M4.16-rdstm-placement; `tools/rdstm_place.py` probe
    + selftest. Join key NOT identified; done-when not met (negative).
  - Claims: C-1810–C-1819

- [ ] **M4.16b — Decode RDSTM per-record field directory (C-884) and re-test placement**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.15
  - Goal: reproduce the per-record length/offset directory walk from bytes to
    recover true TMC field boundaries, then re-run `tools/rdstm_place.py` on
    decoded fields (location/area/front/rear/inter-section).
  - Done when: ≥20 decoded records map to tile/mesh/coordinates with a named
    join key and ~0 random-key control, or the mapping is proven impossible
    with method recorded.
  - Claims: C-1840–C-1849

- [ ] **M4.16c — Verify `INTER`/`FRWAY` `ref` lead as aligned records**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.16
  - Goal: test C-1811 as aligned u32 fields (not byte scan) in `INTER*`/
    `FRWAY*`, decode the mesh/link reference, and test `INTER→tile/mesh→
    coordinate` with random-key control.
  - Claims: C-1950–C-1959

- [ ] **M4.16d — TMC location→segment placement via `TFTBL`/`reception.dat`**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.16b, M4.7
  - Goal: if `RDSTM001` is TMC (C-882), test placement through the TMC
    location table chain rather than raw row bytes.
  - Claims: C-1960–C-1969

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

- [x] **M4.20 — US `DRSTR001` round-trip diff at `0x1ae0`**
  - Status: done · Owner: task/m4.20-us-drstr-roundtrip · Critical: yes
  - Depends: —
  - Goal: M5.6 writes `DRSTR001.DAT` for generated cards, so the model must
    round-trip on both markets. On the untouched US factory tree
    `l2check.py` `drstr_roundtrip` fails at `0x1ae0` (EXP-2026-11-06-M5.12).
  - Input: US image (Shared inputs / M5.12), `tools/drstr.py`,
    `docs/format/drstr.md`, `l2check.py`.
  - Done when: the field at `0x1ae0` is explained in `drstr.md` and the
    rebuild is byte-identical for US (7,456 B) and EU, with a self-test case
    for the US form.
  - Result: EXP-2026-11-06-M4.20-us-drstr-roundtrip; `drstr_ze0.build()` preserves DRSTR-stored entry name case (US `XMD/ltntbl.dat` @0x1ae0); US+EU byte-identical, `drstr_ze0 --selftest` OK.
  - Claims: C-2100–C-2109

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

- [x] **M5.2 — Mesh splitter**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: M4.8, M5.1
  - Done when: every way is assigned to meshes and clipped at borders, and
    `imf_check.py --assign-tiles` agrees.
  - Result: `tools/mesh_split.py` clips ways at cell borders with exact
    intersections and per-side nodes; `imf_check --assign-tiles` agrees
    (EXP-2026-11-06-M5.2-mesh-splitter).
  - Claims: C-1040–C-1049

- [ ] **M5.3 — OSM → Clarion road class/speed table**
  - Status: open · Owner: — · Critical: yes
  - Depends: M4.2
  - Done when: a table covers every `highway=*` value in the region with
    unmapped values listed.
  - Claims: C-1050–C-1059

- [ ] **M5.4 — Tile writer: roads only**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.2 (M5.3 for final classes, not needed to start)
  - Input: `tools/tilewriter.py` (splices road records into a factory tile,
    keeps header/tables and section 4; 48/48 synthetic checks,
    EXP-2026-11-06-M5.4-tilewriter, C-1060); `tools/ze0-viewer/vendor/osm2clarion`,
    factory neighbours, `section4.py preserve`. Use the real EU tile that
    covers Dolnośląskie (`IMG`, rule 11) and a synthetic or small hand-made
    `.osm` for that area (no OSM download needed).
  - Note (PM 2026-11-06): the earlier blocker "no vendor tile here" is not a
    blocker under rule 11. Until M5.3 lands, use a provisional class table
    (each generated road takes the class of the factory road it replaces, or
    the tile's most common local class) and say so in the EXP.
  - Done when: one generated tile from the real factory tile passes L2.
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

- [x] **M5.10 — Card image builder (`tools/mkcard.py`)**
  - Status: done · Owner: task/m5.10-mkcard · Critical: yes
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
  - Result: `tools/mkcard.py` rebuilds the FAT32 partition from a tree while
    copying MBR/pre-partition/tail verbatim; unchanged tree is byte-identical
    and the result passes L1 (EXP-2026-11-06-M5.10-mkcard); real IMG round-trip
    pending.
  - Claims: C-1910–C-1919
  - Result: EXP-2026-11-06-M5.10-mkcard.md — `mkcard.py` copies firmware/pre-partition/0x06000000 verbatim and rebuilds the FAT32 map partition from a tree. Real EU 2011 unchanged-tree rebuild: byte-identical to IMG (SHA-256 `105e2032…76307`, 0 diff ranges), `cardcheck.py --image` PASS (480 files, 194 pairs, 46 tiles). Synthetic self-test OK (sparse FAT32, 0x06000000 preserved, changed-tree fresh build reads back). Diff ranges explained; cannot reproduce SD lock state/CID. `selftest.py` 34 passed.

- [ ] **M5.11 — End-to-end: one generated tile on an accepted card image**
  - Status: open · Owner: — · Critical: yes
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
  - Claims: C-1970–C-1979

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

- [x] **M4.8c — Confirm `coord.py` on the US grid**
  - Status: done · Owner: task/m4.8c-coord-us-grid · Critical: yes
  - Depends: M4.8
  - Goal: target a specific US road by lat/lon, which M5.12 needs.
  - Input: `tools/coord.py`; US tiles use `R ≥ 0xA0` (lon −172…−52, so
    `lon_max = 108 − int(R,16)` goes negative); `LEAF_2011-2012_US.img`
    `COORD001`/tile bboxes; the 52742-vs-52736 origin question (M4.8).
  - Done when: `coord.py` maps ≥ 5 known US landmarks (coordinates from
    Wikipedia/Wikidata, not OSM) into the right US tile and cell within a few
    hundred metres, and the self-test pins a US fixture.
  - Claims: C-1990–C-1999
  - Result: EXP-2026-11-06-M4.8c-coord-us-grid.md. 5 Wikipedia landmarks
    (Statue of Liberty, White House, Golden Gate Bridge, Space Needle, Willis
    Tower) → correct US tiles (`B38R0B0R`,`B38R0B8R`,`B38R0E0R`,`B40R0E0R`,
    `B38R0C0R`), in cell, 189–300 m round-trip. US `COORD001` (11 regions)
    matches EU layout/origin 52742; `MAPAL001` stream key B confirmed origin
    52736 on US (`B38R0B0R` keys inside box only @52736). `coord.py --selftest`
    pins US fixtures (18 checks).
  - Depends: —
  - Goal: an automatic report of what changed vs what was preserved between
    a factory and a generated/mutated tile (sections, records, bytes).
  - Input: `harness.py compare-tiles`, `section4.py`.
  - Done when: `tools/tile_diff.py A B --json` works on a factory tile and
    on the `harness.py mutate` output.
  - Claims: C-1100–C-1109

- [ ] **M5.13 — Patch a file in place inside a factory image (`tools/imgpatch.py`)**
  - Status: done (planning) · Owner: session-ZMxuBT · Critical: yes
  - Depends: — (M5.12 for the edited pair)
  - Goal: the S1/S2 cards for Marek's unit must differ from S0 only in the
    changed file (one variable per card, `card-test-plan.md`). `mkcard.py`'s
    fresh build re-lays out the FAT and drops the root volume-label entry
    `QSD-301-103` (PM check 2026-11-06: factory US root slot 0 is an
    attr-`0x08` entry, BPB label `NO NAME`; M5.12 `cardcheck` warned "no
    volume label").
  - Input: `LEAF_2011-2012_US.img`; `mkcard.py` FAT helpers
    (`open_map_partition`, `_resolve`, `chain`); `mutate_refer_poi.py` and the
    M5.12 edit (`REFER001/POINT010.DAT.cmp`/`.ind`, page `0x840ba0`; 65
    contiguous clusters). Compressed output depends on the zlib build
    (EXP-2026-11-06-H10): record the zlib version and the SHA-256 of every
    file and image you produce.
  - Done when: `imgpatch.py --image IMG --replace REL=FILE … -o OUT` writes the
    new bytes into the file's existing cluster chain (grows/shrinks the chain
    in both FATs and FSInfo only when the cluster count changes) and updates
    the directory entry size; synthetic self-test; on the US image it builds
    **S1** (page `0x840ba0` recompressed unchanged) and **S2** (the M5.12
    rename), and the EXP gives each image's SHA-256 and shows every diff
    range lies in the replaced files' clusters or their directory entries;
    `cardcheck.py --image` passes with the label present. Images stay outside
    the repo; the EXP gives Marek the exact commands to rebuild them locally.
  - Claims: C-2020–C-2029

- [x] **M5.12b — `mkcard.py`: keep the volume label and factory root order on a fresh build**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M5.13 is the path for the hardware cards; this is for M5.11)
  - Goal: a fresh build should not drop the root attr-`0x08` entry
    (`QSD-301-103` US, check the EU label) or reorder the root.
  - Input: `tools/mkcard.py` `build_fresh_partition`/`populate_dir`;
    `cardcheck.py` `_read_volume_label`.
  - Done when: the fresh build writes the source volume-label entry as root
    slot 0 and keeps the source directory order where names match; the
    self-test covers it; the M5.12 rebuild reports the label with no warning.
  - Claims: C-2030–C-2039

- [ ] **M5.12c — Every copy of the renamed POI name on the US card**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M5.12)
  - Goal: tell Marek which screens should show `OSM2LEAF TEST POI1` (map
    label, POI list, name search) and whether an index still holds the old
    name.
  - Input: US tree; decompress all 58 `.cmp` pairs (`cmpind.py`) and scan them
    and every uncompressed file for `HANA HEALTH CENTER`, `HANA HEALTH` and the
    bytes that follow the name in record 0 of page `0x840ba0`.
  - Done when: the EXP lists every hit (file, logical offset, structure);
    if a search/sort index also holds the name, either extend the edit (new
    S2 via M5.13) or state what Marek should expect on screen.
  - Claims: C-2040–C-2049

- [ ] **M5.14 — US geometry edit: move one road vertex (S3)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.13, M4.8c
  - Goal: the first geometry change Marek's unit renders, on the proven
    one-vertex path (M4.4: section 4 preserved, L2 pass on EU).
  - Input: US tree; `tools/tile_diff.py`, `section4.py preserve`, the M4.4
    mutate path, `coord.py` (M4.8c) to pick a recognisable road.
  - Done when: `tile_diff.py` shows only that vertex changed; the US tile
    checks pass (or the US-specific gap is named); M5.13 builds **S3**; the
    EXP names the road, tile and lat/lon before/after so Marek can find it.
  - Claims: C-2050–C-2059

- [ ] **M5.15 — `build.py` writes a card: factory image + OSM → card image → checks**
  - Status: open · Owner: — · Critical: yes
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
  - Claims: C-2280–C-2289

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
- [ ] **M6.2 — S0 on Marek's unit: factory clone of the US card**
  - Status: open · Owner: Marek · Critical: yes · **Runner: non-Claude** (hardware)
  - Depends: — (a spare 16 GB SDHC card; `card-test-plan.md` P1–P6)
  - Goal: prove that a byte-exact clone we write boots the unit; it is the
    control for every later card.
  - Input: `LEAF_2011-2012_US.img` (sha256 `53342430…c5383`, Marek's own card);
    `card-test-plan.md` S0; lock with the unit's own SD LOCK menu (M2.13) or
    the Pico tool (M6.11).
  - Done when: an EXP records the card model, image and read-back SHA-256,
    lock method, screens in order, boot time to map, and the card hash after
    the run; pass/fail per S0.
  - Claims: C-1140–C-1149
- [ ] **M6.5 — S1: no-op recompressed `POINT010` on the US unit**
  - Status: open · Owner: Marek · Critical: yes · **Runner: non-Claude** (hardware)
  - Depends: M6.2, M5.13 (S1 image), **M9.11 + M9.12 pass on the S1 image first**
  - Done when: an EXP records S1 per `card-test-plan.md` (boot, POI list
    opens, no dialog, card hash after the run). A reject here means the unit
    wants factory-exact compressed bytes: stop and re-plan before S2.
  - Claims: C-1150–C-1159
- [ ] **M6.6 — S2: the renamed POI on the US unit**
  - Status: open · Owner: Marek · Critical: yes · **Runner: non-Claude** (hardware)
  - Depends: M6.5, M5.13 (S2 image), M5.12c + M3.12 (what to expect on
    screen), **M9.10 + M9.12 pass on the S2 image first**
  - Goal: see `OSM2LEAF TEST POI1` where `HANA HEALTH CENTER` was (Hana, Maui,
    Hawaii: scroll the map there, and try the POI name search).
  - Done when: an EXP records each screen checked (map label, POI list, name
    search) with a photo and pass/fail.
  - Claims: C-1160–C-1169
- [ ] **M6.7 — S3: display and routing across the moved US road**
  - Status: open · Owner: Marek · Critical: no · **Runner: non-Claude** (hardware)
  - Depends: M6.6, M5.14
  - Done when: an EXP shows the moved vertex on screen and one route that
    uses the changed road.
  - Claims: C-1170–C-1179
- [x] **M6.12 — Clarion debug console (MONI `FW>`, `DSW=0006`) access procedure**
  - Status: in progress · Owner: session-ZMxuBT · Critical: no · **Runner: non-Claude** (needs
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

---

## M7 — Scale and release (later)

- [ ] **M7.1** Full Dolnośląskie run, size budget. Depends M5.6. Claims:
  C-1180–C-1189
- [ ] **M7.2** All-Poland road network. Depends M7.1. Claims: C-1190–C-1199
- [ ] **M7.3** Europe motorway/trunk network. Depends M7.2. Claims:
  C-1200–C-1209
- [x] **M7.4** Profiles schema v2 migration and the writer behind
  `tools/build.py` (validator and `--dry-run` exist, C-564–C-567). Status:
  done · Owner: session-ZMxuBT. All four profiles are v2 and `--strict` clean;
  `build.py --dry-run` prints the M5 stage chain. Result:
  EXP-2026-11-06-M7.4-profiles-v2, C-1210. Claims: C-1210–C-1219
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
  lists the machine. Status: in progress · Owner: session-ZMxuBT · Depends: —. Claims:
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
- [ ] **M8.E4 — Full `Navi.exe` on a generated card (F4 acceptance run)**
  - Status: open · Owner: — · Critical: no
  - Depends: F4 (`Navi.exe` headless, M8.D1/D2 gates), M9.16
  - Goal: the strongest software check before the car: boot the emulated
    unit with a card image and log every map file `Navi.exe` opens and
    every error screen it raises.
  - Done when: the factory US image and the S2 image both reach the map
    state with no error screen, with the file-open logs compared in an EXP.
  - Claims: C-2270–C-2279

---

## M9 — L3 toolkit: run firmware functions against our data

Design: [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md). Code
lives in **`tools/l3_harness/`** (exists: `manifest.py`, `stubs.py`,
`rommap.py`, `runner.py` with `check`/`plan`; `run` is blocked). Pure-Python
parts are covered by `tools/l3_harness/selftest.py`.

- [x] **M9.1 — Module map on the real image**
  - Status: done · Owner: task/m9.1-module-map · Critical: no
  - Depends: — (tool done: `cerom.py memmap`, EXP-48)
  - Done when: `cerom.py memmap` on `IMG256` lists every A + B section,
    `rommap.py convert --skip-compressed` + `validate` pass, and counts per
    module are recorded in an EXP.
  - Claims: C-1630–C-1639
  - Result: EXP-2026-11-06-M9.1-module-map (IMG256 `92aa525d…`); A: 149 modules/527 sections (245 compressed), B: 91/307 (133 compressed). Per-module `rommap.py convert --skip-compressed`+`validate` PASS 239/240; B `nk.exe` sec1 zero-stored-size BSS (vsize 7168, CNT_UNINITIALIZED_DATA) → rommap `size must be positive` (limitation, C-1632). Combined all-module maps overlap at EXE VA 0x11000 (inherent). Counts per module in EXP.
- [ ] **M9.2 — Ghidra project builder**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (Ghidra
    cannot be installed in the Claude sandbox; the tool and `--plan` are done)
  - Depends: M9.1 (M1.6b for thunk labels)
  - Goal: `tools/l3_harness/ghidra_import.py` (pyghidra, headless): all
    A + B sections at their VAs, exports named, thunks labelled, SH-4
    calling convention.
  - Done when: Ghidra shows `OBJDLL!MAL_DataVol_getOffset` at the EXP-50
    call sites and the `HDD_INFO` string xref at `0x004e7d28` (this also
    closes the M1.5 Ghidra check).
  - Blocker: Ghidra 12.2+ and the vendor image are absent; the tool writes and
    validates the two-phase plan (`--plan`, 13 checks) and exits 3
    `MISSING_GHIDRA`. Result: EXP-2026-11-06-M9.2-ghidra-import, C-1640.
  - Claims: C-1640–C-1649
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
- [ ] **M9.6 — First real target: the map-code compare**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M9.5, M2.5 done; M2.15 helps)
  - Goal: run the real `AppLaunch.dll` compare (B `fn 0x03bd2ad8`, M2.5) on
    our `HDD_INFO.TXT` inputs, which unblocks M2.4. (Re-scoped 2026-11-06:
    M2.2's `SD Import` comparator checks user data, not the map; the
    decompressor stays the second target once M1.2c names it.)
  - Input: `tools/l3_harness/runner.py`, `stubs.py` (stub
    `KernelIoControl 0x0101302C` with a target-info record whose `+0x60` holds
    the factory 11 bytes), corpus `hddinfo_variants.py` (M9.7).
  - Done when: `runner.py run` returns a firmware verdict for the factory
    `HDD_INFO.TXT` (accept) and for one edited line-1 variant (reject), with
    the stub log in the EXP.
  - Claims: C-1680–C-1689
- [x] **M9.7 — Corpora** (`hddinfo_variants.py` 89, `ind_mutate.py` 8,
  `DRSTR` and tile mutations) in `tools/l3_harness/corpus.py`, each with
  the Python reader's verdict. Depends: —. Done when `manifest.py build`
  consumes them. Claims: C-1690–C-1699. Done: `l3_harness/corpus.py`
  builds 108 entries (EXP-2026-11-06-M9.7-corpus).
- [x] **M9.8 — `l3check.py`** (L3 rung of the verification ladder). Depends:
  M9.5, M9.7. Status: done · Owner: session-ZMxuBT. Result:
  `tools/l3check.py` runs every target (1 PASS, 5 BLOCKED), exit 3 when
  nothing is runnable (EXP-2026-11-06-M9.8-l3check). Claims: C-1700–C-1709
- [ ] **M9.9 — Keep `l3-ghidra.md` "How to use L3" current.** Done with each
  M9 PR (no separate claim needed).

- [ ] **M9.10 — L3: decode the US POI with the firmware's own reader (software S2)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.11, M9.5
  - Goal: before any card goes into the car, run `Navi.exe`'s own `POINT`
    reader on the decoded factory page and on the renamed page, and read
    the name it returns. Pages are fed already decompressed (the `.cmp`
    layer is M9.11).
  - Input: `tools/l3_harness/runner.py` + `stubs.py`; a new target
    `poi_record_decode` in `targets.json`; US `POINT010.DAT` page `0x840ba0`
    factory and after `mutate_refer_poi.py` (EXP-2026-11-06-M5.12, -H10).
    Corpus files stay outside the repo (hashes only).
  - Done when: `runner.py run poi_record_decode` returns
    `HANA HEALTH CENTER` for the factory page and `OSM2LEAF TEST POI1` for
    the renamed page, record 0, with the stub log in the EXP; plus one
    negative control (a corrupted `len2`) that the reader handles
    differently from the Python parser or the same way, recorded.
  - Claims: C-2140–C-2149

- [ ] **M9.11 — L3: read the edited `.cmp`/`.ind` pair through the firmware (software S1)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.2b (reader VA), M9.10
  - Goal: prove in software what S1 would prove in the car: the firmware's
    `.cmp`/`.ind` layer + its zlib accept our recompressed bytes and return
    the same logical page. Fills the `cmp_ind_reader` target that is
    `blocked` in `targets.json`.
  - Input: M3.2b (`inflate` and the chunk reader), `stubs.py` file I/O
    (`CreateFileW`/`ReadFile`/`SetFilePointer`) over a virtual
    `\Storage Card\REFER001\`; factory, S1 (no-op recompressed) and S2
    `POINT010` pairs.
  - Done when: for all three pairs the firmware reader returns page
    `0x840ba0` byte-identical to `cmpind.py extract`, and chained with M9.10
    yields the expected name; one corrupt-`.ind` case is rejected.
  - Claims: C-2150–C-2159

- [ ] **M9.12 — `l3check.py --card`: the software gate before any car test**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.10, M9.11 (M9.8 for the tool skeleton)
  - Goal: one command that a card image must pass before Marek puts it in
    the unit: run every available L3 target (map-code compare M9.6, `.cmp`
    reader M9.11, POI reader M9.10, later tile reader) on the files that
    differ from the factory image.
  - Done when: `l3check.py --card OUT.img --factory IMG` lists per target
    pass / fail / not-yet-available, exits non-zero on a fail, and the EXP
    shows it on S0 (all pass), S1 and S2.
  - Claims: C-2160–C-2169

- [ ] **M9.13 — L3 target `tile_reader` on factory and generated tiles**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.5 (M3.5 reader VAs `0x0041f26c`/`0x004259bc`/`0x0042757a`; M3.6 helps)
  - Goal: the tile is the core generated format; run the firmware's tile
    reader on it. Fills `tile_reader` (now `blocked`) in `targets.json`.
  - Done when: the reader returns the same level table / section offsets as
    `clarion_tile.read_tile` for one factory tile and for the M4.4 one-vertex
    tile; later for an M5.4 generated tile.
  - Claims: C-2230–C-2239

- [ ] **M9.14 — L3 target `drstr_parser`**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.10, M9.5
  - Done when: the firmware parser accepts the factory `DRSTR001.DAT` (EU and
    US) and one rebuilt by M5.6, and rejects one corrupted case, recorded.
  - Claims: C-2240–C-2249

- [ ] **M9.15 — L3 targets for `ADDRE`, `ZCODE`/`ICODE`/`COORD`, `LCTBL`**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.10 (pattern), and per family M3.13 / M3.14 / M3.15
  - Goal: the same check as M9.10 for every other `REFER001` family; one PR
    per family (title `[M9.15] ADDRE …`), each updating its matrix row.
  - Done when: for each family the firmware reader returns the expected
    value for one factory record and one edited record.
  - Claims: C-2250–C-2259

- [ ] **M9.16 — L3 map-load chain: open a whole card the way `Navi.exe` does**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.11, M9.13, M9.14 (M9.2 Ghidra helps to find the call order)
  - Goal: between single-function L3 and full-system emulation: call the
    firmware's own sequence (`HDD_INFO` → `DRSTR001` → `.cmp`/`.ind` →
    tile / `POINT` readers) against a virtual card tree, with COREDLL file
    I/O stubbed. This is the "mock `Navi.exe`" check of a generated card.
  - Done when: `runner.py chain --tree ROOT` runs the chain on the factory
    US tree without a stub miss, prints each step's verdict, and the EXP
    shows the same run on the S2 tree; `l3check.py --card` (M9.12) calls it.
  - Claims: C-2260–C-2269

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
