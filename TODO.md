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
   free ID of that stream, the full field set, and `Owner: —`. Before
   assigning an ID, `grep` the file for it: parallel merges can add the same
   ID on another branch, and a reused ID (even with different meaning) is a
   board defect. Take the next free claim block from
   [ID allocation](#id-allocation).
10. **Methodology and data rules** in `AGENTS.md` apply to every task: start
    from `tools/cerom.py` for any firmware address (never fitted deltas),
    tools go in `tools/` with a synthetic self-test, observation and
    interpretation stay apart, and **vendor bytes never enter the repo**
    (only offsets, counts, hashes, short header bytes).
11. **Run on the real image before you close.** A firmware or format task is
    not `done` on synthetic data alone, and "no image in the checkout" is not
    a blocker: `python3 tools/fetch_image.py --image IMG256 -o PATH` downloads
    and verifies it in about a minute (see Shared inputs).
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
    *accepted* only when an L3 target (firmware fragment harness) or L4
    full-system emulator run (M8/QEMU) executes that reader on our generated
    file and gets the expected values. Round-trip tools and L2 are necessary,
    not sufficient; L5 (car/bench) is the final oracle when hardware is
    available. Level mapping (2026-11-09): before 2026-11-09 L4=car/bench,
    L5=full-system emulator; after 2026-11-09 L4=full-system emulator,
    L5=car/bench. The live status of each file type is the matrix in
    [`docs/research/reader-coverage.md`](docs/research/reader-coverage.md)
    (H11); update its row in the same PR as your task.

14. **A search task must pass its precheck before anyone searches (PM,
    2026-11-06; premise corrected 2026-11-08).** Three reader tasks (M3.11,
    M3.2b, M3.13) spent a session each reporting "not found in the
    uncompressed sections", and the board blamed compression. That was wrong:
    build A has **0 compressed executable sections** (22.8 MB of code, all
    readable; the 245 compressed sections are `.data` — C-2128). The misses
    were **heuristic**: the pattern came from the format doc, but the code
    used a different one (M3.11's walker reads a packed `u16` with
    `0x3ff`/`0xfc00` masks, no byte tag). So:
    - every task whose subject is a firmware address or reader carries a
      `Precheck:` line whose command can fail, and it separates **executable**
      from data bytes (`tools/reader_precheck.py`, M1.12);
    - state the **signature** the search tests and where it came from: an L3
      run, the writer's inverse, or the format doc (weakest — say so);
    - `Scope:` counts the corpus, `Stop:` says when to report `blocked`
      instead of trying a fourth pattern;
    - a negative never implies "impossible": M3.11's first verdict was
      reversed in one session once the signature changed (C-2129).

15. **A merge re-opens what it unblocks (PM, 2026-11-06, seventh pass).** A
    `blocked` task is not a dead task: it is a ticket waiting for one thing.
    Every blocked task names it in `Unblock:`, and the PR that lands that task
    sets the waiting ones back to `Status: open · Owner: —` in the same commit,
    with the blocker line kept as a note. The negative EXP stays — it is the
    reason the re-run has a `Precheck` and a `Scope`. So M3.13 returns to the
    pool the day M1.2f merges, not before, and not with the same ticket.

16. **Method is a spec, not a narrative (PM, 2026-11-06, eighth pass).** An
    EXP must let another agent reproduce it from the repo plus the named
    sample. Concretely: sample **and** SHA-256 (or `none (tool-only task)`);
    the tool with its version; commands that run as written — a scan that
    lives in a heredoc belongs in `tools/` with `--selftest` (AGENTS rule 7),
    and `# ...` in a Method block is a defect; one positive control and one
    negative control, or an explicit statement why none applies; the corpus
    counted (`282 sections / 23.6 MB`), never "all"; and the falsifier before
    the result. `docs/experiments/TEMPLATE.md` carries the five-part form.
    A task's `Done when` is what makes it `done`: if the check did not pass,
    the status is `blocked`, not `done`.

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
  - Precheck: the command that decides whether the task is possible at all
    (mandatory for any task that searches firmware code or reads vendor data).
  - Scope: the bytes/files the task covers, and what it deliberately excludes.
  - Input: files, offsets, tools, samples.
  - Done when: a check that can fail.
  - Stop: when to set `blocked` and write the EXP instead of a fourth attempt.
  - Unblock: only on `blocked` — the task that turns this one back to `open`.
  - Claims: C-xxx–C-xxx
```

`Precheck`, `Scope` and `Stop` exist because of three sessions lost to
M3.11/M3.2b/M3.13: each reported "not found in the uncompressed sections" — a
true statement about 44 % of build A and 25 % of `Navi.exe` (rule 14).

### Shared inputs

| Name | How to get it | SHA-256 |
| --- | --- | --- |
| `IMG256` (firmware: A, B, C) | `python3 tools/fetch_image.py --image IMG256 -o PATH` (pinned, verified; `curl -r 0-268435455` also works) | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| `IMG` (full EU 2011 card, 7.5 GB) | `python3 tools/fetch_image.py --image EU2011 -o PATH` (resumable) | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| `ROOT` (extracted map tree) | `python3 tools/verify.py --image IMG` (extracts to `archive/work/`) | — |
| `US` (Marek's US 2011 card, 7.5 GB) | `https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img` | `53342430…c5383` |
| `EU2014` (7.4 GB) | `https://files.viaaq.eu/sd-images/LEAF_2014_EU_QSD-357-101.img` | `tools/fetch_image.py --image EU2014` (sha256 `4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b`, H21 verified) |
| `EU2016` (7.4 GB) | `https://files.viaaq.eu/sd-images/ENV200_2016_EU_QSD-390-100.img` | `tools/fetch_image.py --image EU2016` (sha256 `f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb`, H21 verified) |
| Other years/markets | `https://files.viaaq.eu/maps/`, `docs/research/image-versions.md` | record per EXP |

`https://files.viaaq.eu/sd-images/` is reachable from the sandbox; **H16** turns
these rows into one command (`tools/fetch_image.py --list`, `--image KEY`,
`--verify PATH`). Listing is not a
blocker (rule 14 / rule 11).

CE images inside the card image: **A** (apps, `Navi.exe`) `--image-start
0x200200` (copy at `0x2000200`), **B** (kernel + updaters) `0x3e00200` (copy
at `0x4800200`), **C** (kernel + test mode) `0x5200200`. Tools for SH-4 code
in the cloud environment: `apt-get install binutils-sh4-linux-gnu
qemu-system-misc gdb-multiarch`.

## Priorities (PO grooming 2026-11-09; 10th PM pass 2026-11-08 frozen in `docs/research/todo-history-2026-11-06.md`)

**Goal:** OSM-derived maps run in a Nissan Leaf ZE0. SE added/updated since last PO pass (retro 2026-11-09): `M9.12` blocked (S0/S1 no-diff), `M3.18` blocked, `M8.B4` done, `M4.27` blocked, `M3.16` blocked (r2), `M3.20` done, `M4.28` blocked (r2), `M4.32` done, `M4.29` done (r2), plus `M2.18`/`M5.28`–`M5.30` direction tasks. Nearest milestone: **bench/L5 prep** (S1/S2 `M5.13b`, S3 `M5.14`; hardware waits on Marek). Archive 2026-11-09: done, non-blocking, pre-2026-11-09 tasks moved to `docs/research/todo-history-2026-11-09.md`.

### Critical path to "maps run in the car" (L1 → L2 → L3 → L4 → L5)

> Level mapping (2026-11-09): **L3** = firmware fragments (decoder/decompressor/reader harness on our data), **L4** = full-system emulator (QEMU/M8), **L5** = bench/car (M6). Before 2026-11-09, L4/L5 were swapped in some docs.

- **L1 structural (cheap, every card):** `cardcheck.py --image` + `imgpatch`/`rebuild_manifests` diff discipline before L2–L5. Tasks: `M5.13`/`M5.13b`/`M5.24`, `M5.30`, `M6.13`.
- **L2 semantic/offline (cheap):** `l2check`/round-trips/golden/manifest checks; necessary, not sufficient (rule 13). Poland milestones: **`M5.28`** (provisional `highway→Clarion`, L2-testable) → **`M5.29`** (one OSM tile swapped into factory EU card, L1+L2+gate report) → **`M5.30`** (1:1 diff) → **`M5.11`** (Phase-2 acceptance). Supporting: `M5.3`, `M5.22`, `M5.23`, `M5.6`, `M5.21`, `M2.18`, `M5.15`/`M5.26`/`M5.17`/`M5.18`.
- **L3 firmware fragments (virtual, no hardware):** verdicts only when runnable; SKIP/BLOCKED never PASS. **`M9.11b`** registers `cmp_ind_reader` (M9.11 firmware path passes factory/S1/S2+controls, unregistered) → fixes **`M9.12`** `--card` gate (blocked). **`M1.2f`** (DECOMP_BLK, `.data`/sec1) + **`M9.24`** unblock `M9.14`/`M9.17`/data readers; **`M3.11c` → `M9.10`**; **`M9.13`/`M9.6`** re-opened (M9.20 done, may re-block on sec1/globals/IO — record faulting PC). **`M9.27`** records runnable-now S1–S3 evidence; **`M2.4`** uses `M9.6`.
- **L4 full-system emulator (QEMU/M8, software integration):** run original software on the emulated board before L5 where feasible (M8 tasks). Not a substitute for final car acceptance.
- **L5 bench/car (expensive, one variable):** never skip S0. **`M6.2`** S0 (Marek/non-Claude) → **`M6.5`** S1 → **`M6.6`** S2 → **`M6.7`** S3. Prep now: **`M6.13`** S3 manifest, **`H31`/`M9.27`** evidence index/matrix. Run L3/L4 prechecks where runnable before each bench card.

**Take first (ready, critical, unowned):** `M9.11b`, `M5.21`, `M5.28`, `M1.2f`, `M9.24` (after `M1.2f`), `M3.11c`, `M9.27`, `M6.13`, `M5.29` (after `M5.28`/inputs). **Rule 15 applied:** `M4.16b`, `M9.6`, `M9.13` re-opened (M1.11c/M9.20 done) — may re-block with new EXP/faulting PC. **Needs Marek/non-Claude:** `M6.2`/bench, `M6.11` `.uf2`, `M9.2` Ghidra, `M1.2e`, `M6.9`, image/OSM-dependent runs.


## Workstreams at a glance

| Stream | Front | Ready now (no open deps) |
| --- | --- | --- |
| H | Housekeeping | **H19, H27, H28, H29, H30, H31** (see deps); H21/H24/H25/H26 done |
| M1 | Firmware tooling | **M1.2e (non-Claude), M1.2f (critical), M1.2g, M1.12, M1.14**; M1.11c/M1.13/M1.15–M1.17 done |
| M2 | Map code, activation, updater | **M2.4** (re-open: M9.20 done), **M2.18**; M2.14–M2.17 done |
| M3 | Reader contract | **M3.11b, M3.11c, M3.13, M3.16, M3.18, M3.20**; blocked on M1.2f: M3.2, M3.2b, M3.14, M3.15; M3.17 done; M3.19 blocked (→M3.20) |
| M4 | Data formats | **M4.16b** (re-open, M1.11c done), **M4.16c, M4.16d, M4.24, M4.27, M4.29**; blocked: M4.2, M4.3/M4.23 (→M4.24–M4.26), M4.8b (→M4.8d), M4.22 (OQ-44), M4.28 (→M4.27), M4.31; M4.21/M4.25/M4.26/M4.30/M4.32/M4.34 done |
| M5 | Compiler + US edits | **M5.3, M5.5, M5.6, M5.11, M5.14, M5.15, M5.20, M5.21, M5.22, M5.23**; blocked: M5.12c (scan unfinished); M5.4/M5.13b done; M5.16–M5.19 after their M3 readers |
| M6 | Hardware (Marek) | **M6.2 (S0, non-Claude), M6.13** (S3 prep); M6.5/M6.6 after M5.13b+L3 precheck; M6.7 after M5.14 |
| M8 | Full-system emulation | **M8.A2, M8.E1**; M8.A3 after M8.A2 |
| M9 | L3 toolkit | **M9.6, M9.10, M9.11b, M9.12, M9.13, M9.15, M9.18, M9.24, M9.27** (may re-block); blocked on M1.2f: M9.14, M9.17; M9.11/M9.20–M9.23/M9.25 done; M9.2 non-Claude |

**Critical path to a first accepted card:**
· **Software/L3 gate:** **M9.11b** registers `cmp_ind_reader`; **M1.2f** +
**M9.24** unblock M9.14/M9.17/M9.13 and the `.data` readers; **M3.11c** →
**M9.10**; **M9.12** (`l3check.py --card`) is the pre-bench gate. **M2.4**
runs on M9.6's comparator.
· **US (nearest):** S1/S2 exist (M5.13b); Marek runs M6.2 S0 → M6.5 S1 →
M6.6 S2 → (M5.14) M6.7 S3. **M5.21** bounds edited-page slot growth;
**M5.12c** still needs its uncompressed-file scan finished.
· **Poland (goal):** M5.1b/M5.1c (done) → M5.2 (done) → M5.4 (done, limited) →
M5.6 → **M5.11**, gated by M5.3 (road classes), M5.22 (non-`0x2046`
directories), M5.23 (record fields), M5.21 (slot budget) and rule-13
firmware/L3 confirmation.
Supporting: M1.11c → M4.16b → (RDSTM row key) → M4.2/M5.3 · M4.24–M4.26 →
M4.23 → M4.3 · M3.2b → M3.2 → M3.3 · M8.A2 → M8.A3 → M8.A6 (F0).

---

## H — Housekeeping

- [x] **H11 — Reader-coverage matrix: one row per file type we generate**
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
  - Result: `docs/research/reader-coverage.md` (H11 commit / session-ZMxuBT).
  - Done when: `docs/research/reader-coverage.md` has the matrix with
    columns *generate or copy* · format doc · writer tool · offline
    round-trip (L1/L2) · firmware reader VA (M3 task) · L3 target (M9 task) ·
    L3 result · full-system result (M8 F4) — each cell a link, a task ID or
    `—`; every row whose reader or L3 target has no task gets one (next
    free IDs) in the same PR.
  - Claims: C-2170–C-2179

- [ ] **H19 — Re-verify the five thinnest records of the last 24 h**
  - Status: open · Owner: — · Critical: no
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

- [x] **H25 — Fundament CI (GitHub Actions): bramka PR bez danych vendorowych**
  - Status: done · Owner: task/h25-ci-github-actions · Critical: yes
  - Depends: H24 (żeby `selftest.py` nie dawał fałszywego FAIL przez `mkcard`/tmp; H23 zalecane dla higieny TODO)
  - Goal: każdy PR i push do `main` dostaje deterministyczną bramkę jakości sygnału testowego (nie coverage): repo się parsuje, narzędzia mają spójne selftesty, ledger/board są niesprzeczne. To mierzy „czy infrastruktura testów działa”, nie „czy auto czyta kartę”.
  - Precheck: `ls .github/workflows` zwraca brak workflowów (stan bieżący); `python3 tools/selftest.py --list` działa lokalnie. Jeśli istnieje już workflow o tej samej roli, zadanie redukuje się do uzgodnienia z nim (nie duplikować).
  - Scope: nowe pliki `.github/workflows/*.yml` (nazwy ustalone w EXP/PR), uruchamiane na `pull_request` i `push` do `main`. Joba/joby: checkout, Python 3.11 + 3.13 (macierz minimalna; opcjonalnie 3.14 osobno jako informacyjna, bo zlib-ng — patrz H9), `python3 tools/selftest.py` (z jasną polityką SKIP: brak `--selftest`/brak zależności = SKIP, nie PASS), `python3 tools/claims_check.py`, oraz lint TODO gdy H24 dostarczy narzędzie. **Poza zakresem:** pobieranie obrazów vendorowych, testy wymagające `IMG256`/pełnego drzewa, budowa QEMU, L4. Workflow nie może zawierać sekretów ani danych vendorowych.
  - Input: `tools/selftest.py`, `tools/claims_check.py`, `tools/README.md` (konwencje), reguły H9 (zlib-ng nie udaje byte-identical; job kompresji/rebuild oznaczyć lub uruchamiać pod stock zlib). Artefakty: logi, opcjonalnie `selftest --json`.
  - Done when: workflow jest poprawny składniowo, uruchamia się w CI, publikuje czytelne podsumowanie (ile PASS/FAIL/SKIP i które narzędzia zawiodły), a FAIL blokuje merge check; dokumentacja w `tools/README.md` lub `.github/workflows/README.md` opisuje co jest bramką twardą, co informacyjną i dlaczego brak vendor data. EXP z linkiem do przebiegu CI i uzasadnieniem macierzy Pythona.
  - Stop: jeśli `selftest.py` ma niestabilne SKIP/FAIL zależne od środowiska GHA (brak `qemu-system-sh4`, `binutils-sh4`, miejsca na dysku), sklasyfikować je jawnie (SKIP z powodem) zamiast maskować; problematyczne przypadki → osobne taski, status zadania `blocked` z `Unblock:` tylko gdy bramka nie może być zielona z uczciwą klasyfikacją.
  - Claims: C-2750–C-2759
  - Result: EXP-2026-11-08-H25-ci-github-actions.md; added `.github/workflows/ci.yml` (PR/push-to-main, Python 3.11+3.13 hard gate, 3.14 informational/H9, no vendor data/QEMU/L4/secrets) running `selftest --json` + summary, `claims_check.py`, `todo_check.py`; added `.github/workflows/README.md` (hard/informational policy, SKIP≠PASS, why no vendor data). YAML validated (`PyYAML`), local checks: `selftest` 63 PASS/0 FAIL/18 SKIP, `claims_check` OK, `todo_check` OK (0 errors). Draft PR #133 https://github.com/neutrinus/OSM2Leaf/pull/133; first CI run link pending GitHub Actions execution.

- [x] **H27 — Raport postępu L1–L4 (dashboard): reader-coverage + wyniki CI jako artefakt**
  - Status: done · Owner: task/h27-l1-l4-dashboard-r2 · Critical: yes
  - Depends: H25, H26
  - Goal: jeden widok pokazuje postęp celu „karta SD czytana przez auto”, nie jako procent coverage kodu, lecz jako stan warstw: L1/L2 (offline, runnable), L3 (ile targetów PASS/BLOCKED/SKIP, które readery mają VA), L4 (S0–S3: planowane/wynik z EXP/protokołu). Źródłem prawdy pozostają `docs/research/reader-coverage.md`, `claims.md`, `TODO.md` i wyniki narzędzi — dashboard je agreguje.
  - Precheck: istnieją `docs/research/reader-coverage.md`, `tools/l3check.py --help`, `tools/l3_harness/targets.json`; workflow H25/H26 produkuje lub może produkować JSON. Jeśli format któregoś wejścia jest niestabilny, najpierw zdefiniować minimalny kontrakt (osobna sekcja w EXP) zamiast parsować heurystycznie.
  - Scope: narzędzie (nazwa ustalona, np. `tools/progress_report.py` z `--selftest` na syntetycznych danych) lub skrypt workflow generujący `progress.{json,md}`: tabela L1/L2 z ostatniego runu, tabela L3 z `l3check --json` (domyślnie `--build-corpus`; bez vendor firmware jeśli niedostępne), podsumowanie reader-coverage (ile wierszy: writer none/partial/exists, reader unlocated/partial/located, L3 —/blocked/pass), sekcja L4 jako jawny status ręczny (`NOT RUN`/wynik Sx) linkujący do M6/M5 tasków — bez automatycznego PASS. Wynik jako GitHub Actions job summary + artefakt; opcjonalnie commitowany snapshot tylko jeśli bezpieczny (brak vendor danych) i uzgodniony osobno. **Poza zakresem:** GitHub Pages, zewnętrzny serwis, modyfikacja `reader-coverage.md` bez dowodu.
  - Input: `tools/l2check.py --json` (tam gdzie użyte), `tools/l3check.py --json`, `docs/research/reader-coverage.md`, `docs/research/card-test-plan.md` (L4 kontekst).
  - Done when: artefakt z PR/main jasno rozdziela „udowodnione offline”, „udowodnione przez firmware/L3”, „wymaga auta” i nigdy nie podnosi L2 do L3/L4; `--selftest` narzędzia raportu działa bez vendor danych. EXP z przykładowym wydrukiem i mapowaniem pól na regułę 13.
  - Stop: jeśli `reader-coverage.md` nie daje się wiarygodnie zparsować bez zmian semantycznych, raport opiera się na jawnej, małej tabeli pośredniej generowanej/utrzymywanej z kontraktem — decyzja w EXP; nie zgadywać statusów.
  - Claims: C-2770–C-2779
  - Result: EXP-2026-11-08-H27-progress-dashboard.md (C-2770–C-2774); `tools/progress_report.py` (schema `osm2leaf.progress_report/v1`, `--selftest`/`--json`/`--md`, no vendor data) aggregates H26 `l1l2_fixtures` JSON + `l3check --json` + `reader-coverage.md` (explicit matrix contract, no heuristic guess) + bounded TODO/claims + explicit manual L4 S0–S3. Synthetic L3 PASS is never firmware proof; L4 never auto-passed. Example: rc 30 rows, firmware proof 0, L4 NOT RUN, problems 0. `progress_report --selftest` OK, `claims_check` OK.

- [ ] **H28 — L3 w CI: corpus syntetyczny, targety runnable/blocked, opcjonalny tryb z IMG256**
  - Status: open · Owner: — · Critical: no
  - Depends: H25, M9.12/M9.20 (stan bieżący harnessu; zadanie adaptuje się do aktualnych możliwości, nie wymusza PASS na blocked readerach)
  - Goal: pokazywać postęp L3 jako „które czytniki firmware da się uruchomić na naszych danych i jaki jest werdykt”, z uczciwym `BLOCKED` dla niepodłączonych readerów. Nawet 1 runnable target (`probe-zlib-cmf`) to test ścieżki wykonawczej, nie akceptacja karty.
  - Precheck: `python3 tools/l3check.py --build-corpus --selftest` przechodzi lokalnie; `targets.json` istnieje. Sprawdzić aktualne statusy (wiele `blocked` — to oczekiwane).
  - Scope: (1) domyślny job CI: `l3check --build-corpus --json` na corpus syntetycznym; raportuje PASS/FAIL/SKIP/BLOCKED per target; `BLOCKED` nie jest FAIL, brak runnable targetów = exit zgodny z `l3check` (obecnie 3) i jawny status `NO RUNNABLE TARGETS`. (2) osobny workflow `workflow_dispatch`/scheduled (opcjonalny): jeśli polityka repo pozwala, pobiera `IMG256` przez `tools/fetch_image.py --image IMG256` do cache, uruchamia `python3 tools/realcheck.py IMG256` i ewentualne kroki L3 wymagające firmware head — tylko gdy narzędzia i czas GHA na to pozwalają; wynik oznaczony jako „firmware-head regression”, nie pełne L3 na karcie. **Poza zakresem:** pełne obrazy 7GB w standardowym PR job, Ghidra/QEMU jako wymóg PR, fałszowanie PASS.
  - Input: `tools/l3check.py`, `tools/l3_harness/*`, `tools/fetch_image.py`, `tools/realcheck.py`, `IMG256` (tylko tryb opcjonalny, cache, weryfikacja SHA-256).
  - Done when: PR job publikuje tabelę L3 z countami; tryb opcjonalny ma udokumentowane limity (czas, cache, brak pełnego ROOT) i nie uruchamia się automatycznie na każdym PR bez uzasadnienia kosztu. EXP zinterpretowany zgodnie z regułą 13.
  - Stop: jeśli pobranie IMG256 jest niestabilne/niedozwolone w docelowym runnerze, tryb opcjonalny zostaje wyłącznie `workflow_dispatch` na self-hosted/approved runnerze z dokumentacją — nie blokuje PR joba.
  - Claims: C-2780–C-2789

- [ ] **H29 — L5 (hardware/Marek, car): automatyzacja przygotowania artefaktów i rejestracji wyników S0–S3**
  - Status: open · Owner: — · Critical: no
  - Depends: H27, M5.13b (S1/S2 istnieją), M6.2/M6.5–M6.7 (protokół)
  - Goal: L5 (bench/car) nie da się zautomatyzować w GHA (wymaga auta), ale da się zautomatyzować przygotowanie paczki testowej i powtarzalną rejestrację wyniku, żeby postęp L5 był widoczny w tym samym systemie co L1–L4.
  - Precheck: `docs/research/card-test-plan.md` i taski M6.2/M6.5–M6.7 opisują S0–S3; `tools/imgpatch.py`/artefakty S1/S2 są dostępne tam, gdzie budowane (vendor data poza repo). Sprawdzić aktualny stan: M5.13b done, bench czeka na Marka.
  - Scope: (1) `workflow_dispatch` „prepare-L5-bundle” (lub narzędzie; nazwa robocza v1 „prepare-L4-bundle” — traktować jako alias) przyjmujący ścieżki/artefakty dostarczone poza repo lub budowane na self-hosted runnerze z dostępem do vendor data: generuje manifest (SHA-256 obrazów, diff zakresów jak w M5.13b, wersja narzędzi, profil/test id), checklistę S0–S3 i szablon wyniku (PASS/FAIL/objaw, zdjęcie/serial/log opcjonalnie) — bez commitowania obrazów. (2) Szablon EXP/issue lub `docs/experiments/` snippet do wklejenia wyniku Marka tak, by H27 mogło policzyć L5 (car; v1 alias `l4`) jako `Sx PASS/FAIL/NOT RUN`. **Poza zakresem:** zdalne sterowanie autem, automatyczny werdykt L5, przechowywanie obrazów kart w repo/artefaktach publicznych.
  - Input: `docs/research/card-test-plan.md`, M6.2/M6.5–M6.7, H27 format raportu, `tools/imgpatch.py` metadata.
  - Done when: da się jednym poleceniem/workflow wygenerować kompletną paczkę „co nagrać na kartę + co sprawdzić + gdzie wpisać wynik”, a wynik L5 (car) da się odczytać maszynowo przez H27 bez interpretacji prose. EXP z przykładowym bundle manifestem (syntetyczne ścieżki/hashe przykładowe, nie vendor).
  - Stop: jeśli polityka bezpieczeństwa/udostępniania obrazów jest niejasna, workflow tylko generuje checklistę/manifestspec i zatrzymuje się przed pakowaniem binariów — `blocked` z pytaniem do właściciela danych.
  - Claims: C-2790–C-2799

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

- [ ] **M1.4 — Extract compressed `FILESentry` payloads**
  - Tool: `cerom.py files --extract --decompress` writes stored bytes,
    classifies OK/UNSUPPORTED/FAIL and never writes a wrong-length decode
    (EXP-55, C-573); EXP-51 says the real payload is not a stdlib format.
  - Status: blocked · Owner: task/m1.4-extract-filesentry-payloads · Critical: no
  - Blocker: all 8 compressed build-B FILESentry payloads carry CE-LZXD block marker `0x8d80805b` and no public/stdlib `cecompress` method decodes them (0 matches, 8 UNSUPPORTED); M1.2b/c path does not suffice, so `rsize`-length decode / readable `ceconfig.h` cannot be produced without the CE-LZXD codec (M1.2f blocked, M8.E1 runtime unavailable in session).
  - Unblock: M1.2f (CE-LZXD block decode, pure-Python or verified reference) and/or M8.E1 runtime oracle producing verified decodes; then resume M1.4 (decode to `rsize`, add `extract-file NAME` if still desired, verify build C).
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
  - Claims: C-680–C-683

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

- [ ] **M1.2f — Port the nk.exe block codec (`DECOMP_BLK`) to pure Python**
  - Status: blocked · Owner: task/m1.2f-decomp-blk-python · Critical: yes
  - Depends: — (M8.E1b verified the VAs; M1.2a/M1.2d frame the payload)
  - Goal: decode every `IMAGE_SCN_COMPRESSED` section without QEMU. M8.E1b
    ended the address question; what is missing is the codec inside
    `0x8803a384`, not the entry point. **Sixth pass: this is the single gate
    for the software side** — M3.2b and M3.11 both ended at "the reader is in
    Navi.exe sec1", so M9.10 and M9.12 wait here too.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 comphdr --all | tail -1` (expect 245 HOLDS) and `python3 tools/sh4dis.py IMG256 nk.exe --image-start 0x3e00200 --va 0x8803a384 --count 5` (LE prologue decodes). Positive control passed on `IMG256 92aa525d…` (245 HOLDS, EXP-49 headers/markers verified).
  - Scope: build A 245 `IMAGE_SCN_COMPRESSED` sections (187 form 1, 58 form 2) on `IMG256`; build B nk.exe decompressor chain `DECOMP_WRAP/SECT/BLK`/helpers inspected by LE SH-4 disassembly. Excludes a guessed codec, QEMU runtime decode (unavailable here), and 245/245 pure-Python decode (not achieved).
  - Input: `DECOMP_BLK 0x8803a384` (8-byte block header, block type 4/E8,
    LZXD-like — M1.2c, M8.E1b), `DECOMP_SECT 0x88037464` (3-byte frame sizes,
    form 1/2 block loop), `DECOMP_ALLOC 0x88034d94`; `tools/cecompress.py`
    (LZSS/LZX-stored already present), `tools/cedecomp.py`; the two EXP-49
    sections (file `0x01580ce0` len `0x2c6`, `0x015aca7c` len `0x68c`) as the
    positive control; `IMG256`/`IMG` for the other 243.
  - Done when: `cedecomp`/`cecompress` decodes EXP-49 sec1 to `0x484` and sec2
    to `0xcc0` with no QEMU, and `cerom.py decompress --check` reports
    `245 OK` (or lists the exceptions with their bytes); one self-test vector
    is taken from the disassembly.
  - Stop: done-when not met — no pure-Python CE-LZXD block codec without guessing; `sh4dis.py` leaves shift encodings as `.word` in codec paths and `qemu-system-sh4` is unavailable for a runtime oracle (negative EXP recorded).
  - Blocker: CE-LZXD/`0x8d80805b` block codec inside `DECOMP_BLK`/`DECOMP_SECT` not ported rigorously; `cerom.py decompress --check` = 245 `UNSUPPORTED`, `qemu-system-sh4` missing, `sh4dis.py` cannot decode key shift encodings in the inspected paths.
  - Unblock: extend `sh4dis.py` to decode the missing SHAD/SHLD/shift encodings in `DECOMP_BLK/SECT/0x8803a248` (and/or validate a CE XIP LZXD reference against EXP-49), and/or obtain a `qemu-system-sh4` (LE) runtime oracle for `DECOMP_SECT/BLK` with kernel-context handling (M8.E1 path); then resume M1.2f with EXP-49 `--selftest` vectors and `245 OK`.
  - Re-opens on merge (rule 15): **M3.2b, M3.11, M3.13, M9.10** and the
    precheck-gated **M3.14–M3.16, M3.18**; M1.3/M1.4 follow directly. Re-open applies only when M1.2f merges as `done` (this commit is `blocked`).
  - Claims: C-2360–C-2369
  - Result: EXP-2026-11-08-M1.2f-decomp-blk-python (blocked; framing/EXP-49 vectors verified on IMG256, 245 UNSUPPORTED, no QEMU/complete SH-4 decode for a rigorous pure-Python CE-LZXD port).


- [ ] **M1.2g — `decomp_oracle.py` fragment API + CE XIP LZXD reference vector harness (unblocks M1.2f verification)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M1.2f (framing/tree landed), M8.E1b (VAs)
  - Goal: give M1.2f a verifiable oracle/reference path without guessing 245/245: a harness feeds block/section fragments and compares decoded bytes/hash to a trusted reference (QEMU/runtime oracle when available, or a pinned CE XIP LZXD reference output with licence/URL/SHA-256), proving the bitstream/tree variant.
  - Precheck: `python3 tools/cedecomp.py --selftest` passes; EXP-49 vectors and M8.E1b VAs recorded; `python3 tools/decomp_oracle.py --selftest` passes (contract implemented: `osm2leaf.decomp_oracle/v1`, pinned EXP-49 lengths/targets, `vectors --json`, `verify`; extend with `source`/`entry_va`/`input_hash` when wiring M8.E1c/M9.29 runtime output).
  - Scope: `tools/decomp_oracle.py` (stdlib, `--selftest`) schema/result verification for EXP-49/fragment mode + optional wiring to M8.E1c/M9.29 runtime output. No 245/245 claim; no vendor bytes committed.
  - Input: M1.2f `XipLzxd` framing, EXP-49, M8.E1b `DECOMP_SECT/BLK`, M8.E1c/M9.29 JSON when available; external reference requires recorded licence/URL/SHA-256 (non-Claude if download needed).
  - Done when: schema documented and `--selftest` has synthetic controls; EXP-49 sec1/sec2 reports `PASS` only with a trusted decoded reference hash, else `FAIL`/`NO_ORACLE` (never silent pass). M1.2f/M9.29/M9.30 consume the schema; at least one runtime or pinned-reference result is recorded in an EXP.
  - Stop: if no trusted reference obtainable (no QEMU, no licensed reference output), keep EXP-49 `NO_ORACLE` with blocker named and land/keep schema + synthetic selftest.
  - Claims: C-3240–C-3249
- [x] **M1.13 — Find the encoder that reproduces the factory `.cmp` streams**
  - Status: done · Owner: claude/m1.13-factory-encoder · Critical: yes
  - Depends: — (M3.2b names Navi.exe's static zlib 1.1.3, C-2061)
  - Goal: M5.12c renamed 131 of 136 POI records. The five left sit on pages
    whose edited stream is larger than the original slot: stock zlib 1.3.x at
    levels 1–9 is 0.8 % larger than the factory encoder on the same bytes. No
    slot-fit strategy works until an encoder reproduces the factory bytes.
  - Input: `tools/mutate_refer_poi.py` (`page_encoder` tries zlib levels and
    memLevels on the original stream; none matches), the M5.12c EXP on branch
    `claude/m5.12c-poi-copies` (`POINT001–009` factory pages; not yet merged),
    the `REFER001/POINT0xx.DAT.cmp`
    of the US card (`archive/sd-images/LEAF_2011-2012_US.img`), C-2061.
    Candidates: zlib 1.1.3, zlib 1.2.x, zlib-ng, libdeflate, zopfli-style optimal
    parsing.
  - Done when: a tool reproduces the factory inner stream byte-for-byte for at
    least 20 pages of `POINT001–009` (count and list in the EXP), with a
    negative control (a changed byte gives a different stream), and the
    candidate that matches is named with its version. If none matches, the EXP
    lists every candidate's byte difference and the status is `blocked`.
  - Result: EXP-2026-11-08-M1.13-factory-encoder. 471/471 inner pages of POINT001–009 reproduced exactly by stock zlib L6/memLevel 8 (release-indistinguishable, 1.1.3 to 1.3.2); zlib-ng 0/471; `tools/factory_zlib.py` added. The "0.8 % larger" premise is not reproduced (C-2575).
  - Claims: C-2570–C-2579

- [x] **M1.10b — Spot-check two resolved import names at their call sites**
  - Status: done · Owner: task/m1.10b-import-spotcheck · Critical: no
  - Depends: — (M1.10 done)
  - Goal: M1.10 named 846/846 `Navi.exe` slots by export-table lookup. Two of
    the newly named exporters (`XGLDLL`, `OSMDLL`) should be confirmed where
    they are **called**, so the resolution is not just a plausible name.
  - Precheck: `cerom.py imports Navi.exe --resolve-with 0x200200 --resolve-with
    0x3e00200 --resolve-with 0x5200200` must list both names.
  - Scope: two slots, one call site each; no new naming pass.
  - Done when: for one `XGLDLL!` and one `OSMDLL!` name, `sh4xref.py --calls`
    (or the thunk table) shows the call site and the argument shape matches the
    export's role; recorded in an EXP with the slot VAs.
  - Stop: if a call site cannot be found, say so and stop — a name without a
    caller stays `OBSERVED`.
  - Claims: C-2600–C-2609
  - Result: EXP-2026-11-08-M1.10b-import-spotcheck. `OSMDLL!OSM_Printf` slot `0x0055d954` confirmed at `fn 0x0039c978`/`0x0039c9ba` (4 args, printf-style-consistent; 88 loads/24 pools); `XGLDLL!xglDisable` slot `0x0055db94` at `fn 0x003da074`/`0x003da0aa` (2 args, `r5=0x00800000`, capability-consistent; 42 loads/21 pools). Names via M1.10 export resolution; exact prototypes UNKNOWN. Selftest/claims_check green.

- [x] **M1.16 — Unify `.cmp`/`.ind` chunk codec and inner-page helpers across tools**
  - Status: done · Owner: task/m1.16-cmpind-unify · Critical: no
  - Depends: — (M1.13 done: factory params pinned to stock zlib L6 / memLevel 8
    / wbits 15 / default strategy for POINT001–009)
  - Goal: reduce drift in the format we must generate correctly (rule 13).
    `cmpind.py`, `cmpind_writer.py`, `mutate_refer_poi.py`,
    `mutate_refer_page.py`, `poi_copies.py`, `slot_budget.py`, `lev3456.py`,
    `l2check.py` and others reimplement `CHUNK=0x10000`, `decompressobj` loops,
    `compressobj` params, pair read/write and inner-zlib-page iteration with
    slightly different defaults and error handling. M5.21 already noted slot/encode
    logic duplicated with M5.12c.
  - Precheck: `python3 tools/selftest.py` passes for the affected tools
    (baseline; record any current failures separately) and
    `grep -rn 'CHUNK = 0x10000\|decompressobj\|compressobj' tools/*.py | wc -l`
    shows the duplication surface.
  - Scope: add one shared module (extend `tools/cmpind.py` or add
    `tools/cmpind_codec.py`, name chosen in the PR) exposing decode/encode,
    changed-chunk repack, inner complete-zlib-page iteration, and a
    `factory_compress`/`factory_params` helper aligned with M1.13/C-2570–C-2579.
    Migrate the highest-risk writer tools first (`cmpind_writer`, `slot_budget`,
    `mutate_refer_poi`/page, `poi_copies`); leave read-only tools if migration
    risk is higher than benefit, but document the decision.
  - Done when: the shared module has `--selftest` (round-trip, changed-chunk
    repack preserves unchanged bytes, factory params reproduce a known vector),
    migrated tools keep their existing selftests green, and no migrated tool
    hardcodes conflicting default zlib params.
  - Stop: if a migration changes bytes produced for a real factory sample,
    record the before/after SHA-256 and stop that tool's migration until the
    difference is explained (encoder version vs logic bug).
  - Claims: C-2730–C-2739
  - Result: EXP-2026-11-08-M1.16-cmpind-unify. Added `tools/cmpind_codec.py`
    (factory params L6/m8/w15/default, outer decode/encode/changed-chunk repack,
    inner complete-zlib-page helpers; `--selftest` 21 checks). Migrated
    `cmpind_writer`, `slot_budget`, `mutate_refer_poi`/`mutate_refer_page`,
    `poi_copies`, `cmpind.py`, `lev3456.py`; all existing selftests green, no
    conflicting factory-param defaults. `selftest.py`: passed=67 failed=0
    skipped=15; `claims_check.py`: OK. `ind_mutate`/`l2check`/fit-fallback
    duplications left documented (C-2736).

## M2 — Map code, activation, updater

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
  - Status: blocked · Owner: task/m2.4-predict-hdd-info-variants · Critical: yes
  - Depends: — (**M9.6 merged** `ff8720d`, M2.15 and M2.3 done); the corpus and
    the comparator are both on `main` now
  - Note (sixth pass): the old blocker ("firmware verdicts need the L3 target,
    unavailable offline") was **wrong** — M9.6 runs the comparator offline with
    a stubbed `KernelIoControl(0x0101302C)`, and M2.15 supplied the exact card
    bytes plus the `+96`/`+112`/`+114` unit fields. Only M9.6 is missing.
    The offline model-M0 gives 66 ACCEPT / 23 DIFFERENT
    (EXP-2026-11-06-M2.4-hddinfo-variants).
  - Blocker: M9.6 is merged (`ff8720d`) and M9.20 module-entry plumbing is on
    `main`, but no runnable `AppLaunch.dll` B `fn 0x03bd2ad8` module target is
    wired (`KernelIoControl(0x0101302C)`/HDD_INFO FS stubs + `0x01f74b30` parse
    cache per M2.5/M2.15); M9.6 remains blocked and `hddinfo_compare`/
    `mapcode_comparator` targets are blocked, so no firmware verdicts can be
    produced.
  - Unblock: M9.6 — reopen and complete its done-when by wiring/running the real
    `fn 0x03bd2ad8` comparator; then reopen M2.4 and produce per-variant
    firmware verdicts compared with `hddinfo.py classify`.
  - Goal: run the real parser + comparator on `tools/hddinfo_variants.py`.
  - Input: L3 runner (M9.5), corpus (M9.7). The map-code comparator is
    `AppLaunch.dll` `fn 0x03bd2ad8` (M2.5), not M2.2's user-data check.
  - Done when: each variant has a firmware verdict and it is compared with
    `hddinfo.py classify`.
  - Result: blocked — EXP-2026-11-08-M2.4-hddinfo-variants-blocked (negative:
    firmware verdicts unavailable; C-2086 retains M2.15-model offline
    reclassification of all 89).
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

- [x] **M2.15 — The exact `HDD_INFO` bytes behind `DIFFERENT MAP CODE` and `MAP DATA BASE UNMATCH`**
  - Status: done · Owner: task/m2.15-hddinfo-bytes-mapcode · Critical: yes
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
  - Result: EXP-2026-11-06-M2.15-hddinfo-bytes-mapcode. Check 1 (0x50, B
    `fn 0x03bd2ad8`/C `0x03bb2858`): HDD_INFO line 1 `base_code` slot 0 bytes
    0-10, file off `0x00` len 11 vs `KernelIoControl(0x0101302C)` +0x60 (11 B).
    Check 2 (0x51, B `fn 0x03bd2ce4`/C `0x03bb2a64`): line 3 `build` pos 5,6,7
    (file off 31-33 factory) → 3 nibbles `MapDBVer=((d5*16)+d6)*16+d7` (fn
    `0x03bd2a40`, `0-9a-fA-F`→0-15) vs target +112 min/+114 max (u16 BE);
    parse cache global `0x01f74b30` (16-byte slots). `validation.md` and
    `hddinfo.py classify` (M2.15 model, self-test 44 checks, pass+fail per
    check) updated. 89 M2.4 variants reclassified (M2.15): check 1 69 PASS /
    20 `DIFFERENT MAP CODE`, check 2 89 `BOUNDS_UNKNOWN` (unit bounds unknown),
    10 MapDBVer changes noted.
  - Claims: C-2080–C-2089

- [x] **M2.18 — Offline HDD_INFO / MAP CODE acceptance predictor (pre-L3 gate)**
  - Status: done · Owner: task/m2.18-hddinfo-predictor · Critical: yes
  - Depends: M2.3, M2.5, M2.15 (done)
  - Goal: give M5.11/M5.15 and card builders an L2-adjacent, offline verdict for the two known acceptance checks (M2.5 `DIFFERENT MAP CODE`: 11 bytes `KernelIoControl(0x0101302C)+0x60` vs `HDD_INFO` line 1; M2.15 `MAP DATA BASE UNMATCH`: `MapDBVer` range) without waiting for a runnable M9.6 firmware target. This does **not** replace M9.6/M2.4 firmware verdicts (rule 13).
  - Precheck: `python3 tools/hddinfo.py --selftest` passes and pins the M2.15 model; `tools/hddinfo_variants.py` corpus is present. If factory `+0x60` or range bounds cannot be stated from recorded EXPs/claims, report `BOUNDS_UNKNOWN` (never pass).
  - Scope: extend `hddinfo.py` or add a small stdlib tool (name stated in PR, `--selftest`) to classify `HDD_INFO.TXT` as `ACCEPT`/`DIFFERENT MAP CODE`/`MAP DATA BASE UNMATCH`/`BOUNDS_UNKNOWN`; re-classify the 89 variants offline. No firmware run.
  - Input: EXP-2026-11-06-M2.5, EXP-2026-11-06-M2.15, `tools/hddinfo.py`, `tools/hddinfo_variants.py`, `docs/format/validation.md`.
  - Done when: per-variant table (89 rows) with positive/negative control per check; unknown bounds never produce a pass verdict; M5.11 can call it on a candidate `HDD_INFO.TXT`; EXP states which verdicts still require M9.6/M2.4.
  - Stop: if `+0x60`/bounds inputs cannot be stated from recorded evidence (not guessed), stop short of a pass verdict.
  - Claims: C-3030–C-3039
  - Result: docs/experiments/EXP-2026-11-09-M2.18-hddinfo-predictor.md

- [ ] **M4.23 — Tile section-2 regulation/connectivity reader (kinds `0x2046`/`0x3e4`)**
  - Status: blocked · Owner: claude/m4.23-restriction-encoding · Critical: no
  - Blocker: part b (odd-record) grammar is not decoded; the regulation-word test fails its pre-stated 0.80 threshold (37 % at level 1, 55 % at level 2, shuffle 4 %); no firmware reader VA for grid section 2 is located.
  - Unblock: M4.24 (part b), M4.25 (word test) and M4.26 (VAs and coarse addressing); each re-opens this task when it merges.
  - Depends: — (M4.3 is blocked on exactly this)
  - Goal: M4.3 decoded the OSM side of a turn restriction but found no
    documented tile-side layout: `rd_check` reads only kind `0x1046` (3 of 5
    local tiles stop), and the `tools_ze0` writer's `0xff` regulation words are
    unverified. Without this, restrictions cannot be written or even checked.
  - Precheck: `tools/tile_diff.py`/`harness.py` list the section-2 kinds in the
    five pinned tiles; at least one tile must expose `0x2046`/`0x3e4` (if none
    does, the finding is "not present on these tiles").
  - Scope: section 2 of the five pinned tiles; one junction with a known
    restriction (M4.3's `r120176`); no writer.
  - Input: EXP-2026-11-08-M4.3 (the OSM record and why the tile side stops),
    `tools_ze0` section-2 reader, `map-tiles.md`, `rd_check` behaviour.
  - Done when: the record layout for the two kinds is decoded and one
    regulation word is matched to the known restriction (or shown absent with
    a control), with VAs where the firmware reads it (M3.6/M3.16 overlap is
    fine to cite).
  - Stop: if the kinds are not in these tiles, record the census and stop.
  - Claims: C-2620–C-2629
  - Result: EXP-2026-11-08-M4.23-restriction-encoding — unit-0 grammar of kinds
    `0x2046`/`0x1046`/`0x3cde`/`0x03e4` established (C-2620–2621); pairing (C-2622);
    part b not decoded (C-2623); arrivals carry no words, against the writer (C-2624);
    `r120176` to-entry carries `0x23ff` (C-2626); `no_*` word test 37 %/55 % vs shuffle
    4 %/3 %, FAIL (C-2627); firmware VAs not located (C-2629).

- [ ] **M4.24 — Section-2 part-b (odd record) grammar, levels 2, 4 and 5**
  - Status: blocked · Owner: task/m4.24-sec2-partb-grammar-r2 · Critical: no
  - Depends: — (the census and checker are in `tools/rd_restrictions.py`, M4.23)
  - Goal: decode the unit-1 layout of the odd records that `rd_restrictions.py census` reports as mismatched (mark word, node blocks, entry words, side words).
  - Precheck: `python3 tools/rd_restrictions.py census` on `B28R070R.DAT` and `LEV3456R.DAT` reproduces the part-b notes in EXP-2026-11-08-M4.23.
  - Scope: odd records of `0x2046` (B28R070R level 2) and `0x03e4` (LEV3456R level 5); no writer.
  - Input: EXP-2026-11-08-M4.23-restriction-encoding (part-b table), `tools/rd_restrictions.py` (`part_b_check`).
  - Done when: a parser reproduces every odd record of those two tiles (76 + 34 pairs) word for word, with its own `--selftest`, and the mark and side words are explained by the parent record, not fitted.
  - Stop: after two rounds of fitting without a full match, record a negative EXP and stop.
  - Unblock: re-run M4.24 when mark (`w[1]`), `nb[2]` (side), `nb[3]`, `e[1]`, `e[2]` and the L5/L4 node ordering are derived as deterministic functions of the parent record (no fitting), then reproduce all 76+34 odd records word for word.
  - Claims: C-2880–C-2889 (was C-2630–C-2639, collision fixed by H23)
  - Result: blocked, EXP-2026-11-08-M4.24-sec2-partb-grammar. Precheck reproduced M4.23. Structural skeleton parsed for all 76 L2 + 34 L5 pairs (`[nn,mark,(nb[4]=deg<<12,ni,?,? , e[3]*deg)*nn,parcel_code]`, L2 index order, L5 permutation, `e[0]=other`/`other&0x3fff` for L5 cross-parcel 8166/8166); mark/side/nb3/e1/e2 and L5 ordering not explained by parent record, so word-for-word reproduction not achieved (done-when unmet). No C-288x claims registered.

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
  - Unblock: M3.2b's re-run (the chunk engine and its caller), or M1.2f when
    the `.ind` layer turns out to be in `Navi.exe` sec1.
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

- [x] **M3.6 — Which tile sections the renderer reads**
  - Status: done · Owner: task/m3.6-tile-sections-renderer · Critical: no
  - Depends: M3.5
  - Done when: each tile section has "read by VA" or "ignored" in
    `map-tiles.md` (section 4 especially).
  - Result: EXP-2026-11-06-M3.6-tile-sections-renderer (MAP_DATA `0x00425f40`=renderer, RGD_DATA `0x004266ec`=router, shared `0x0041ee14`; LEV sec1→MAP, sec2→RGD; grid sec1→MAP; sec4 no read VA in MAP/RGD paths, C-870–C-876).
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
  - Status: blocked · Owner: task/m3.2b-cmp-chunk-reader-inflate · Critical: yes
  - Depends: — (**not** M1.2f for the code: no executable section of build A is
    compressed, C-2128)
  - Blocker: no literal-pool/direct/32-bit reference to `0x0041c7e8` in any
    uncompressed section of build A (282 sections, 149 modules) or B/C; the
    likely indirect-call pointer lives in `Navi.exe` sec1 (`.data`,
    `0xc8002040`, compressed) which `cerom decompress` cannot decode
    (`UNSUPPORTED`, LZX/LZSS). Zlib is in uncompressed sec0 (C-2060), so the
    Done-when escape is false. A firmware `.cmp`-open L3 probe for the caller
    PC needs file-stub/import binding (M9.24 context). M3.2a/b unanswered.
  - Unblock: decode `Navi.exe` sec1 and resolve the indirect slot to a sec0
    `jsr @Rn` caller (M1.2f/M8.E1/working CE codec), or capture the `0x41c7e8`
    caller PC via an L3 firmware `.cmp`-open run with file stubs (M9.24).
  - Re-opened (ninth pass, 2026-11-08): pass-1 "caller in compressed code"
    refuted (sec1 is `.data`, C-2128/C-2129). Pass 2 (this PR): searched
    `tools/sh4scan` anchors/signatures across builds A/B/C, exhaustive 32-bit
    and pool xrefs across all uncompressed sections — 0 refs to `0x41c7e8`;
    sec1 `UNSUPPORTED` by `cerom decompress`; direct-call chunk engine OK
    (M9.11) but not a firmware caller-PC probe.
  - Goal: M3.1/M3.2 show the `MAL_DataVol_*` and `.IND` string leads miss the
    reader. Every `.cmp` chunk is zlib, so the reader must call `inflate`.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 $IMG sections Navi.exe`
    and `python3 tools/sh4scan.py $IMG --image-start 0x200200 anchors` — verify
    sec0 uncompressed, sec1/2 compressed `.data`, anchors present (14 hits).
  - Scope: build A 527 o32 sections (282 uncompressed, 23,559,542 B psize, all
    149 modules) + builds B/C module census/targeted search; map-module
    signature scans `{Navi.exe, OSMDLL.dll, NaviMapCC.dll, OBJDLL.dll,
    MAL_DataVol.dll, STDDLL.dll}`; **excludes** undecoded compressed sec1/sec2
    `.data` and a firmware open-path L3 run (needs file stubs).
  - Input: image A modules (`cerom.py sections`); zlib message strings
    (`incorrect header check`, `invalid distance too far back`,
    `invalid stored block lengths`), the zlib version string and the
    `inflate … Copyright` banner as anchors; `sh4xref.py --to`;
    `tools/sh4scan.py`; `docs/format/cmp-ind.md`.
  - Done when: the module and VAs of `inflateInit2_`/`inflate`/`inflateEnd`
    are recorded, their callers are listed, and the caller that loops over
    `chunk_offset[]` is named (then answer M3.2's two questions); or the EXP
    shows, with a positive control, that zlib sits in a compressed section.
  - Stop: 0 readable refs to `0x41c7e8` across all uncompressed sections of
    builds A/B/C and sec1 undecodable by available codec → set `blocked` with
    the negative EXP (do not guess the caller or fabricate a codec result).
  - Result: EXP-2026-11-08-M3.2b-cmp-chunk-reader-inflate-2.md (blocked, pass 2).
    Inflate/engine VAs confirmed (C-2061–C-2063); 0 refs to `0x41c7e8` in all
    uncompressed sections of A/B/C (C-2064 strengthened); sec1 `.data`
    `UNSUPPORTED` by `cerom decompress` (C-2067); `.ind` consumer/indirect
    caller unresolved, M3.2a/b open (C-2066 refined). Pass 1:
    EXP-2026-11-06-M3.2b-cmp-chunk-reader-inflate.md.
  - Claims: C-2060–C-2069

- [x] **M3.11 — The `POINT` record reader in `Navi.exe`**
  - Status: done (walk; name-copy split to M3.11c, byte order to M3.11b)
    · Owner: — · Critical: yes
  - Depends: — (**not** M1.2f: no compressed section of build A is code, C-2128)
  - Goal: the function that walks a decoded `POINT0xx` page (`tag,len2`
    records, `0x60`/`0x68`, record size `2*len2`) and copies a POI name out.
    It is the first target of the software check of the US rename (M9.10)
    and of every later POI edit.
  - Result: EXP-2026-11-06-M3.11-point-reader.md (pass 1, C-2120–C-2127, `b6f491a`) + EXP-2026-11-07-M3.11-point-reader-2.md (pass 2, C-2128–2129,C-2540–2546, walker `fn 0x003f5194`, `tools/point_walk_l3.py`, `4843efa`).
  - Result, pass 1 (2026-11-06): `EXP-2026-11-06-M3.11-point-reader.md`,
    C-2120–C-2127 — access path `0x003fbed8` → `0x0040b358` → `0x004125a8`
    (`0x14e8` → `REFER001`+`INDEX003.DAT`); no `#0x60/#0x68` tag test and no
    `@(1,Rm)` length read anywhere (still true). Its blocker "walker in
    compressed sec1" is **refuted** (C-2129): sec1 is `.data` (`0xc8002040`).
  - Result, pass 2 (2026-11-07): `EXP-2026-11-07-M3.11-point-reader-2.md`,
    C-2128, C-2129, C-2540–C-2546, tool `tools/point_walk_l3.py`.
    **Walker = `fn 0x003f5194(r4=page, r5=n)` → pointer to record n or 0.**
    The header is one big-endian u16: `type = w>>10` (`0x60`→`0x18`,
    `0x68`→`0x1a`), `len = w & 0x3ff` words, `0xfc00` escape = `0x4e8` words,
    `len 0` ends. Run from the ROM bytes in PySh4 (LE) on the real US
    `POINT010` page `0x840ba0` it returns the `parse_page` offsets (9/9
    sampled n, incl. the end); the unswapped page fails (negative control).
  - Hints for the next agent (what is known, what to skip):
    - **Do not** search for `cmp/eq #0x60`, `#0x68`, `and #0xf7`,
      `mov.b @(1,Rm)`: the firmware never tests the tag byte. Search for the
      masks `0x03ff`/`0xfc00` (`point_walk_l3.py consts`: 35 + 13 loads,
      cluster `0x3f39d6–0x3f8d54`, the `HDLMAP_*` layer).
    - **Do not** wait for M1.2f: `point_walk_l3.py sections` → 0 compressed
      executable sections. "No caller found" = indirect call through a
      pointer in `.data` (sec1), not hidden code.
    - Page API: dispatcher `0x003f5cdc` (buffer table `0x00d53500`), skip-n
      `0x003f39c0`, globals page base `0x00d5e4e4` / count `0x00d5e4d0`
      (getter `0x003f3314`), escape test `0x003f8a0c`, body `rec+4`
      (`0x003f5c40`), 8-byte trailer (`0x003f5c90`).
    - Name side: start from the debug dump `fn 0x003a03b4` (strings
      `" pPoiStr     : %s"` `0x3ceac`, `" nPoiLen     : %d"` `0x3cec0`) →
      `sdl_poi_get_data_recorde` `fn 0x003cd910(db, rec, out)` → name accessor
      `fn 0x003d1150(ctx, rec, &ptr)` (`len = rec[14]`, `ptr = rec+21`; else
      `0x003d09a0` splits on the byte at `*0x005628e8`), copy `0x003d1188`.
      The offsets do not match POINT record 0 (name at `+0x5e`) — M3.11c.
    - Debug strings are rich (`[SDL]…`, `sdl_poi_*`, `HDLMAP_*`, 27,996
      printable runs in sec0): `sh4xref --to <string-1>` when a string has no
      pool hit (the pool often points one byte earlier, at a `\n`).
    - `PySh4` is big-endian (C-2546): reuse `point_walk_l3.le_engine()` until
      M9.21 lands.
  - Done when (whole task): `firmware.md` names the record-walk function
    (done) and the name-copy function with VAs, arguments and output, each
    tied to the record framing in `refer.md`.
  - Claims: C-2120–C-2129, C-2540–C-2549

- [ ] **M3.11b — Where the `POINT` page becomes native u16**
  - Status: blocked · Owner: claude/m3.11b-point-byteorder · Critical: yes
  - Blocker: the page is handed to the walker by an `OSM_TaskSend` reply from another task (OSMDLL import 12, `fn 0x3f40ec`); no 16-bit swap loop exists in Navi.exe sec0 or OSMDLL sec0 (C-2547, C-2548).
  - Unblock: M9.11 (the dynamic run shows the buffer the walker is handed; M9.11 is itself blocked on M9.11b, and its decoder output is file order, so the swap is downstream of `0x41c7e8`)
  - Result: EXP-2026-11-08-M3.11b-point-byteorder (negative; done-when not met).
  - Depends: — (M9.11 helps: its run shows the bytes the chunk decoder hands back)
  - Goal: `0x3f5194` reads `mov.w @page` and only walks a 16-bit-swapped
    page (C-2541). Find the code that swaps the inflated page (or copies the
    record) before the walker, so M9.10 feeds the firmware what the unit
    feeds it, not our guess.
  - Precheck: `python3 tools/point_walk_l3.py walk IMG256 --cmp … --ind …
    --page 0x840ba0 --page-len 42848` passes (needs the US pair, EXP
    M3.11-2 "Method" shows the range fetch).
  - Scope: Navi.exe sec0 only (all code). Already excluded: a
    `mov.w`/`swap.b`/`mov.w` loop with a back-branch (0 of 4,884 `swap.b`).
  - Input: try in order — (1) writers of `*0x00d5e4e4` / `0x00d53500` slots
    (`sh4xref --to 0x00d5e4e4`: `0x3f3314`, `0x3f39b4`, `0x3f3a00`,
    `0x3f40c2`, `0x411df4`); (2) byte-pair swaps written as
    `mov.b`+`shll8`+`or`, or 32-bit `swap.b; swap.w; swap.b`; (3) the tail of
    `0x41c7e8` / `0x542148` (M3.2b); (4) dynamic: run M9.11's chunk decoder,
    then watch the buffer.
  - Done when: VA + loop of the swap (or proof that the walker gets a copy),
    with the factory page swapped by the firmware code itself in PySh4 and
    byte-equal to `point_walk_l3.swap16`.
  - Stop: after (1)–(3) without a hit, write the EXP and let M9.11's dynamic
    run answer it.
  - Claims: C-2547–C-2549 (C-2540–C-2546 unchanged)

- [ ] **M3.11c — The name accessor for a `POINT` record**
  - Status: blocked · Owner: task/m3.11c-point-name-accessor · Critical: yes
  - Blocker: end-to-end PySh4 of the identified accessor
    (`0x003f632c`/`0x003f5e78` → `0x003f61bc`/`0x003f5d98` field 5) on record 0
    requires HDLMAP page context (`0x00d53500` handle table + indirect
    `*0x0055d8f0`) in compressed `.data` (sec1, C-2128); without context it
    faults (PySh4 `UnmappedAccess 0x0055d8f0`), so the Done-when name string
    return (`HANA HEALTH CENTER` / M5.12 `OSM2LEAF TEST POI1`) cannot be
    produced. VAs/args/chain identified and sub-accessors PySh4-verified.
  - Unblock: M1.2f/M8.E1 (readable `.data`/globals) or a stubbed HDLMAP page
    context for `0x003f51e0`/`0x003f56bc`; then run `0x003f632c`/`0x003f5e78`
    (or `0x003f61bc` field 5) on rec0 and the M5.12 renamed page in PySh4 and
    mark done if names match.
  - Depends: — (M3.11b only for the final L3 run)
  - Result: EXP-2026-11-08-M3.11c-point-name-accessor.md (C-2920–C-2927).
    Accessors `fn 0x003f632c(r4=db,r5=rec)→ptr` / `fn 0x003f5e78→len` dispatch
    to field 5 via `0x003f61bc`/`0x003f5d98` for normal 0x60xx
    (`0x003f8a0c`→-1); used by `sdl_poi_get_data_recorde` `0x003cd910` status-1
    path (`0x3cdc30`/`0x3cdc1a`). SDL `fn 0x003d1150(rec[14]/rec+21, fallback
    0x003d09a0/*0x5628e8)` refuted for raw display name (C-2545, PySh4 len 0).
    Raw name is `ff ff`-delimited suffix (rec0 `+0x5e`, 999/1000 on page
    `0x840ba0`). `docs/format/firmware.md` records VAs/args/chain.
  - Goal: the function that turns a `POINT` record (record 0 of US page
    `0x840ba0`: `60 40 8f 9c …`, name `HANA HEALTH CENTER4590@HANA HWY` at
    `+0x5e`) into the name string the UI shows — VA, args, output.
  - Precheck: `sh4xref --to 0x3ceac` hits `fn 0x003a03b4` (the dump).
  - Scope: Navi.exe sec0, functions reachable from `0x003cd910`,
    `0x003d1150`, `0x003d1188`, `0x003cc93c`, `0x003f5c40`, `0x003f6220`, and
    the other `0x3ff` sites in `0x3f5900–0x3f9400`.
  - Stop: if the accessor needs `bt/s`/`bf/s`, do M9.21 first.
  - Claims: C-2920–C-2929 (was C-2548–C-2549, overlap with M3.11b fixed by H24)

- [x] **M3.12 — `INDEX003.DAT`: is it the POI name search index?**
  - Status: done · Owner: task/m3.12-index003-poi-search · Critical: yes
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
  - Result: `INDEX003.DAT` absent from EU 2011 and US 2011 stock FAT/DRSTR
    (EU REFER001 388/0 INDEX*, US 116/only INDEX001; firmware string refs at
    US 14679280/46136560, EU 14648088/46105368, no FAT file). No `INDEX003`
    entry refers to HANA HEALTH CENTER on these images; S2 POI rename does
    not need to update `INDEX003` on these images. Record layout UNKNOWN
    (needs an image that ships the file). EXP-2026-11-06-M3.12-index003-poi-search.
  - Claims: C-2130–C-2139

- [ ] **M3.13 — The `ADDRE` (address) reader**
  - Status: blocked · Owner: task/m3.13-addre-reader · Critical: yes
  - Blocker: `fn 0x003f56bc` (sec0) is confirmed as the sole 0xc000-class header
    gate consuming ADDRE `c0/c8/c1` tag-class (C-973 partial, C-2184), but the
    done-when is not met: no consuming instruction VA named for C-970–C-972,
    C-974–C-977 or the sequential `2*L` record-stream cursor/token walk, and
    unmapped fields are not proven "never read" (second signature family /
    `0x00d53500`→ADDRE buffer-slot binding needed). Access-path L3 probe
    blocked by COREDLL/state (`0x0040b358`→`-1`, `0x0040114e` FPU-unmodelled).
  - Unblock: bind `0x00d53500` buffer slots to ADDRE and L3-trace
    `0x003f56bc`/`0x003f5d98` with decoded ADDRE data to map sub-table
    `+24/+26/+12` → C-971/C-972/C-977; run a second signature family for
    C-974–C-976 token consumers (name `TT LL 00 ff`, range, point `TT 40`
    in native/swapped form) scoped to REFER `0x003f51e0` callees.
  - Depends: — (**not** M1.2f: no executable section is compressed, C-2128)
  - Re-opened (ninth pass, 2026-11-08). The pass-1 blocker ("parser in sec1")
    is refuted the same way as M3.2b's. What the search proved is narrower: no
    parser matching the **M4.9 byte grammar** exists in executable bytes. The
    POINT lesson (C-2129) is that the firmware may pack differently — a native
    `u16` with masks, not the byte tag/len the doc extrapolated. Re-run with
    `tools/sh4scan.py` on the masks/strides the writer implies, plus an L3
    probe on the mapped `0x14e8`/`ADDRE0` path (`0x003fbed8` →
    `0x0040b358` → `0x004125a8`, `fn 0x0040114e`).
  - Depends: — (M3.11 shows the pattern for `REFER001` families)
  - Goal: confirm the `ADDRE` grammar (M4.9) against the code that reads it.
  - Input: id table `0x00179338` (`ADDRE0`), name builder `0x003fbed8`, lookup
    `0x0040b358`, descriptor switch `0x004125a8`; `refer.md`, EXP-2026-11-06-M4.9.
  - Done when: `refer.md` names the reader VA(s) and maps each grammar field
    (C-970–C-979) to the instruction that consumes it, or lists the fields
    the firmware never reads.
  - Claims: C-2180–C-2189
  - Result: `EXP-2026-11-08-M3.13-addre-reader-2.md` (C-2180–C-2187, partial; refines `EXP-2026-11-06-M3.13-addre-reader.md`). Writer-implied native `u16` class-mask signature finds `fn 0x003f56bc` (Navi.exe sec0, `0x003f56ec`) — sole `*r5 & 0xe000 >= 0xc000` (`cmp/hs` literal `0xc000`, 1/82 loads) gate, accepts ADDRE `c0/c8/c1` (C-973 tag-class mapped). Resolves via `0x003f51e0` (`0x00d53500`, POINT family); callers `0x003f5d98`/`0x003f61bc`. C-970–C-972, C-974–C-977 + sequential `2*L`/token consumers not mapped (done-when not met). L3: `0x0040b358`→`-1`, `0x0040114e` FPU-unmodelled. `refer.md`/`firmware.md`/`reader-coverage.md`/`claims.md` updated.

- [ ] **M3.14 — `ZCODE` / `ICODE001` / `COORD001` readers**
  - Status: blocked · Owner: claude/m3.14-reader-layout · Critical: yes
  - Blocker: no reader body for `ZCODE0nn` or `COORD001` is in decodable build-A code (their names have no plain literal load; `ICODE001` has only the opener `fn 0x003f2cc0`), so the done-when is not met (C-2190–C-2199).
  - Unblock: M1.2f
  - Result: EXP-2026-11-08-M3.14-reader-layout (negative for ZCODE0/COORD001, partial for ICODE001; done-when not met).
  - Depends: — (M4.12 already decoded the layout from bytes; this task only
    looks for the consuming code)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` (M1.12) — build A
    has **0 compressed executable sections** (C-2128), so "not found" means the
    *signature* was wrong, not that the bytes are hidden. Test a structural
    signature derived from an L3 run or the writer's inverse, not the byte
    grammar in `refer.md` (that assumption is how M3.11's walker was missed,
    C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code. `Stop:` after two signature families fail — then
    `blocked` + EXP listing the signatures tested.
  - Goal: the region/index/coordinate tables decide where a generated
    Poland map lives; confirm their layout (C-110, C-1992,
    `coord-zcode-icode.md`) from the code.
  - Input: id table `0x00179338` (`ZCODE0`), `coord-zcode-icode.md`, M4.8c, M4.12.
  - Done when: `coord-zcode-icode.md` gives the reader VA per file and which
    fields each one uses, with VAs.
  - Claims: C-2190–C-2199

- [ ] **M3.15 — The `LCTBL001` name-table reader**
  - Status: blocked · Owner: claude/m3.15-lctbl-reader · Critical: yes
  - Blocker: the record walker and string decoder are reached only through compressed `Navi.exe` sec1 helpers (`0x0055d924`, `0x0055d954`), and no inflate table is in decodable bytes (C-2200–C-2206).
  - Unblock: M1.2f
  - Result: EXP-2026-11-08-M3.15-lctbl-reader (negative; done-when not met).
  - Depends: M1.2f (M3.7 located the `LCTBL001.DAT` load at `0x004125a8`; rule 14 precheck put the target in compressed bytes)
  - Precheck: `tools/reader_precheck.py --module OBJDLL.dll` (M1.12) — all
    executable sections are readable (C-2128); OBJDLL's compressed bytes are
    data. Derive the signature from an L3 run or the writer's inverse, not from
    the doc grammar (M3.11's lesson, C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code. `Stop:` after two signature families fail — then
    `blocked` + EXP listing the signatures tested.
  - Goal: Polish street/place names go through this table (M4.18 framing,
    M3.9 collation); confirm framing and encoding from the code.
  - Done when: `refer.md` (or `rdstm.md`) names the record-walk and
    string-decode VAs and states the encoding the code assumes.
  - Claims: C-2200–C-2209

- [ ] **M3.16 — `INTER` / `FRWAY` readers**
  - Status: blocked · Owner: task/m3.16-inter-frway-readers-r2 · Critical: no
  - Blocker: no content reader VA consuming INTER/FRWAY 12-byte table / blob fields found in decodable build-A Navi.exe sec0 (5.56 MB, 0 compressed exec sections, C-2128) after two structural writer-inverse signature families (12-byte scan + 0xffff@+8 + add#12; 0x1108 construction) returned 0 hits; consumed-field mapping unknown (C-2211–C-2213). Shared REFER001 access path is confirmed (C-2210).
  - Unblock: derive a field-level/inter-family consumption signature from a writer inverse or L3/`.data` dispatch trace (M4.16c ref lead, M1.2f/M8.E1 for compressed `.data` pointer tables if needed) with a positive control, or locate the generic container/indirect reader that consumes the 12-byte table+blobs.
  - Depends: — (M4.16c for the `ref` lead)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` (M1.12) — build A
    has **0 compressed executable sections** (C-2128), so "not found" means the
    *signature* was wrong, not that the bytes are hidden. Test a structural
    signature derived from an L3 run or the writer's inverse, not the byte
    grammar in `refer.md` (that assumption is how M3.11's walker was missed,
    C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code. `Stop:` after two signature families fail — then
    `blocked` + EXP listing the signatures tested.
  - Done when: the reader VAs and consumed fields are in `refer.md`.
  - Claims: C-2210–C-2219
  - Result: `EXP-2026-11-08-M3.16-inter-frway-readers-r2.md` (negative/blocked; done-when not met). Shared REFER001 access path confirmed: `INTER0`/`FRWAY0` in volume-id table `0x00179338` (~VA `0x0017934c`/`0x00179354`, C-881), descriptor `0x14e8` `fn 0x004125a8` → `REFER001`+`INDEX003.DAT` via `jsr 0x0040b358`, name-builder `fn 0x003fbed8` path (C-880/C-2180/C-2210). Two writer-inverse signature families over Navi.exe sec0 (5.56 MB, 0 compressed exec, C-2128) found 0 content-reader candidates (C-2211); consumed fields `UNKNOWN` (C-2213). `refer.md` INTER/FRWAY sections and `claims.md` C-2210–C-2214 updated.

- [ ] **M3.18 — `ICADM0nn` / `ZIPFR001` readers (H11 G2)**
  - Status: blocked · Owner: task/m3.18-icadm-zipfr-readers-r2 · Critical: no
  - Depends: — (M3.11/M3.13 show the access-path pattern for `REFER001`
    families and the same compression wall)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` (M1.12) — build A
    has **0 compressed executable sections** (C-2128), so "not found" means the
    *signature* was wrong, not that the bytes are hidden. Test a structural
    signature derived from an L3 run or the writer's inverse, not the byte
    grammar in `refer.md` (that assumption is how M3.11's walker was missed,
    C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code. `Stop:` after two signature families fail — then
    `blocked` + EXP listing the signatures tested.
  - Goal: the two families with no reader task at all. Both carry content a
    Poland card must generate (`ICADM` country/admin terms, `ZIPFR`
    postal/freeway masks), so a wrong writer is undetectable today.
  - Input: id table `0x00179338`, name builder `0x003fbed8`, lookup
    `0x0040b358`, descriptor switch `0x004125a8`; `refer.md` ICADM/ZIPFR
    sections (C-136, C-137); `reader-coverage.md` rows 14–15.
  - Done when: `refer.md` names the reader VAs and the fields each consumes
    (or shows the firmware copies the block and reads no field, with a
    positive control), and matrix rows 14–15 carry the result.
  - Blocker: Done when not met after two writer's-inverse signature families in
    build-A uncompressed executable scope (22.8 MB): (1) ICADM stride/tag pool
    constants `0x01CE`/`0x00E7` → 0 Navi.exe / 0 ICADM-attributable hits; (2)
    ZIPFR 14-byte stride `add #14` in Navi.exe sec0 (79 sites) with no
    confirmed 10-byte-key+`u32`-mask record consumer and no exec literal-pool
    xref to `ZIPFR001.DAT` (`0x178e08`). Access-path/opener evidence named
    (`ICADM0` `0x178c60`, `REFER001` `0x178c68`; `fn 0x003f1640` ICADM
    name-builder+`0x0040b358` resolver, xref'd from `fn 0x003f2cc0` context),
    but no field-consuming reader VA/field map and no copy-only positive
    control. Navi.exe sec1 is 16.8 MB compressed `.data` (3560 indirect slot
    calls; C-2128: exec readable, data compressed) — a reader reached only via
    sec1 pointers is out of static decodable scope.
  - Unblock: resolve Navi.exe sec1 indirect/pointer-table targets for REFER001
    family openers (compressed-` .data` recovery context) and re-run
    structural signatures over resolved targets; and/or obtain an L3/runtime
    trace from `0x003f1640`/REFER001/ZIPFR open to first field access that
    names reader VAs/consumed fields or demonstrates copy-only with a positive
    control.
  - Result: EXP-2026-11-08-M3.18-icadm-zipfr-readers (negative/partial,
    C-2380–C-2385; `refer.md`/matrix rows 14–15 NOT updated — reader VAs/field
    consumption not established).
  - Claims: C-2380–C-2389

---

- [ ] **M3.19 — `tools/sh4scan.py`: commit the scan that produced the three negatives**
  - Status: blocked · Owner: claude/m3.19-sh4scan · Critical: yes
  - Unblock: M3.20 (name the register-AND mask variant; correct M3.11's pattern text).
  - Blocker: M3.11's mask count 1 is not reproduced: its one site (Navi.exe `0x3715c8–0x3715cc`) is `mov #0x70,R3; and R3,R0; cmp/eq #0x60,R0`, a register AND, and `and #0x70,R0` + `cmp/eq #0x60` finds 0. The other seven published counts reproduce. See EXP-2026-11-08-M3.19-sh4scan.
  - Depends: —
  - Goal: M3.11, M3.13 and M3.2b are correct negatives that **cannot be
    re-run**: the tag/stride/mask searches are prose plus heredocs, and M3.2b
    contains `# ... anchor search over IMG256 ...`. Rule 16 makes that a
    defect; this task fixes it and gives M1.12 its engine.
  - Precheck: the counts to reproduce are published — 527 build-A o32 sections,
    26 aligned `cmp/eq #0x60` and 23 `cmp/eq #0x68` hits in `Navi.exe` sec0,
    0 tag pairs, 1 `and #0x70`+`#0x60` mask hit, 0 `@(1)+2*L` stride
    candidates, 282 sections / 23.6 MB for the M3.13 corpus, 14 zlib markers.
    If the tool cannot reproduce them, the published numbers are the problem —
    report that, do not adjust the tool to fit.
  - Scope: build A (and B/C on `--image-start`); LE halfwords; uncompressed and
    compressed sections both listed, with the compressed share printed.
  - Input: EXP-2026-11-06-M3.11, -M3.13, -M3.2b (counts and patterns),
    `cerom.py memmap --json`, `sh4xref.py`; `capstone` must not be required
    (a pattern scan is halfword arithmetic, not disassembly).
  - Done when: `python3 tools/sh4scan.py IMG --image-start 0x200200 tags
    --module Navi.exe`, `--pattern <hex>`, `stride`, `mask-pair` and `anchors`
    run on `IMG256`, reproduce every count above, print the corpus in bytes and
    sections, and `--selftest` pins the pattern semantics on synthetic
    halfwords (including the misaligned false positives M3.11 rejected); M1.12
    imports it rather than duplicating the scan.
  - Stop: if the counts differ, record the discrepancy in an EXP and stop —
    the difference is the result.
  - Claims: C-2530–C-2539

- [x] **H37 — 24h senior-engineer review: completed tasks and experiments**
  - Status: done · Owner: task/h37-24h-se-review · Critical: no · Pair: solo
  - Depends: —
  - Goal: audit tasks completed in the 24h window for `Done when` compliance, EXP/TEMPLATE.md quality, claim reproducibility, and retired-lead traps; add follow-up tasks where defects or deepening opportunities exist.
  - Scope: commits `88332de..65e6ae2` on `origin/main` (2026-11-08 24h window); sampled EXPs and TODO task blocks; cheap tool selftests and `claims_check.py`/`todo_check.py`. No vendor-image reruns beyond selftests, no QEMU/Ghidra.
  - Input: `git log --since=24.hours origin/main`, `docs/experiments/EXP-2026-11-08-*` added in range, `docs/experiments/TEMPLATE.md`, `AGENTS.md`, `TODO.md`, `docs/research/claims.md`.
  - Done when: EXP `docs/experiments/EXP-2026-11-09-H37-24h-se-review.md` records the audit (commands, controls, scope, falsifier, observations/interpretation) and TODO contains the follow-up tasks from this pass.
  - Claims: C-3130–C-3139
  - Result: EXP-2026-11-09-H37-24h-se-review.md (80 commits 88332de..65e6ae2 audited; 7 follow-up tasks added H38/H39/M4.35/M5.31/M5.32/M9.28; claims_check OK; sampled selftests OK; no done-task status reversals).

- [ ] **H38 — `selftest.py`: discover and run `tools/l3_harness` selftests**
  - Status: open · Owner: — · Critical: yes · Pair: solo
  - Depends: —
  - Goal: prevent L3 harness regressions from bypassing the main selftest gate (M9.20 noted `tools/selftest.py` does not discover `l3_harness/`).
  - Scope: `tools/selftest.py` discovery/wiring and/or a thin wrapper; run `tools/l3_harness/selftest.py` (and any `l3_harness` tools with `--selftest` that fit the suite contract) as part of `python3 tools/selftest.py`. No behavior changes to harness logic.
  - Input: `tools/selftest.py`, `tools/l3_harness/selftest.py`, `tools/l3_harness/dispatch.py --selftest`, `tools/l3_harness/engine.py --selftest`, `tools/l3_harness/runner.py selftest`, `tools/l3_harness/ghidra/l3_run.py --selftest`; EXP-2026-11-08-M9.20.
  - Done when: `python3 tools/selftest.py` reports the l3_harness checks (or a named aggregate) and exits non-zero on harness selftest failure; `python3 tools/selftest.py --only l3_harness` (or documented selector) works if selectors are supported; SKIP/blocked cases remain honest (e.g. Ghidra/QEMU absent). `tools/README.md` updated if needed.
  - Stop: if `l3_harness` selftests require environment assumptions incompatible with the main suite, integrate them as an explicit sub-suite with clear SKIP reasons and keep the main gate green only when the sub-suite passes or is honestly skipped.
  - Claims: C-3160–C-3169

- [ ] **H39 — `ze0-viewer/harness.py info`: tolerate opaque/unparseable records**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: —
  - Goal: make tile inspection usable on factory tiles that contain opaque/bad records (M5.4 noted `harness.py info` crashes with `zlib.error` on `B48R058R`; `harness.py verify` still runs).
  - Scope: `tools/ze0-viewer/harness.py` `cmd_info`/info path only. No parser behavior changes in `tools_ze0` unless required and isolated; prefer catching/reporting bad records with counts and offsets.
  - Input: `tools/ze0-viewer/harness.py`, `tools/ze0-viewer/tools_ze0/` readers, EXP-2026-11-08-M5.4 (Observation 3/7 notes), EXP-2026-11-08-M9.22 (opaque B30R048R context).
  - Done when: `python3 tools/ze0-viewer/harness.py info <tile>` on a tile containing the known opaque/bad-record pattern reports the records as bad/opaque with counts (and does not crash), while `verify` behavior remains unchanged for the checked cases; a synthetic or minimal fixture covers the crash path if practical, otherwise the EXP records the real-tile command/result and SHA-256.
  - Stop: if the crash is inside vendored `tools_ze0` and cannot be fixed without changing pinned vendor behavior, document the limitation, add a targeted wrapper/fallback in `harness.py`, and file a follow-up naming the vendored function.
  - Claims: C-3180–C-3189

- [ ] **H40 — L1/L2 generated-fixture contract: deterministic in-process fixture + coherent ZE0 card/tree builder (no vendor data)**
  - Status: open · Owner: — · Critical: yes
  - Depends: H26
  - Goal: close H26 gaps (`L1 synthetic`/`L2 tile` NOT COVERED where feasible) with a tiny deterministic in-process fixture representing generated content (roads/names/POIs/geometry) and a coherent ZE0 card tree/image that `cardcheck.py --root/--image` and targeted L2 round-trips can run on in CI (no network, no OSM download, no vendor data).
  - Scope: test infrastructure only. Procedural/committed fixture (no vendor dump, no downloaded OSM extract) and a minimal builder producing coherent DRSTR/MMAIN/tile level tables/headers/REFER001/top-level layout as current tools support. Do not claim firmware acceptance (rule 13); no full M5 compiler coverage.
  - Input: `tools/l1l2_fixtures.py`, `tools/cardcheck.py`, `tools/mkcard.py`, `tools/drstr_ze0.py`, `tools/tilewriter.py`/harness, `tools/imgpatch.py`; AGENTS data rules.
  - Done when: `python3 tools/<name> --selftest` builds the fixture in a temp dir, runs `cardcheck.py` and reports L1 PASS/FAIL per check (JSON), and runs >=1 coherent synthetic L2 round-trip (tile/DRSTR/POI) where supported; CI-safe/deterministic; H26 registry gains runnable entries only where truly covered, else honest NOT COVERED with updated reason.
  - Stop: if coherent MMAIN/tile/DRSTR cannot be produced without vendor bytes, deliver the smallest coherent subset with explicit NOT COVERED per uncovered file/feature and follow-up tasks naming missing writer/structure; never fake PASS.
  - Claims: C-3270–C-3279

- [ ] **H41 — L1/L2 progress matrix for generated card: per file + per feature (roads,names,POIs,geometry) with regression baseline**
  - Status: open · Owner: — · Critical: yes
  - Depends: H40, H26
  - Goal: progress signal for a generated fixture: L1 pass/fail per file/check and L2 pass/fail per file and per feature (`roads,names,POIs,geometry`), with SKIP/NOT COVERED/NOT RUNNABLE separate and never counted as PASS; CI fails on fixture regression.
  - Scope: extend `tools/l1l2_fixtures.py` or add a companion reporter (name in PR) consuming H40 fixture; emit JSON/Markdown with stable keys `level,file,feature,status(PASS|FAIL|SKIP|NOT_COVERED|NOT_RUNNABLE),command,reason`. Feature mapping explicit/evidence-based (tile road records/section-1 geometry -> roads/geometry, DRSTR/name entries -> names, POI mutation/records -> POIs; unmappable -> NOT COVERED). Committed no-vendor baseline for named fixture; baseline changes intentional with EXP/PR explanation.
  - Input: `tools/cardcheck.py --json`, `tools/l2check.py --json` where usable on generated fixture, `tools/l1l2_fixtures.py`, H40; `.github/workflows/l1l2-fixtures.yml`.
  - Done when: CI artifact includes per-file/per-feature matrix for generated fixture; `--selftest` covers status separation and baseline-regression detection (synthetic PASS->FAIL fails gate); adding a check is registry/data, not report-logic surgery; workflow README states regression policy.
  - Stop: if feature attribution cannot be made without guessing format semantics, report NOT COVERED with missing claim/tool reference.
  - Claims: C-3280–C-3289

- [ ] **H42 — Wire progress dashboard and L1/L2/L3/L4-emu/L5-bench status into CI artifacts/job summaries (no vendor data)**
  - Status: open · Owner: — · Critical: yes
  - Depends: H27, H41, H28
  - Goal: make the per-level progress signal visible on every PR/push: publish `progress.json/md` (H27 schema) plus H41 per-file/per-feature matrix as artifacts/job summaries.
  - Scope: workflow changes only (extend existing workflows or add `progress.yml` as appropriate); no vendor data, no IMG256/ROOT, no QEMU/M8 run in PR gate, no L5 bench execution. Integrate H28 L3 synthetic summary when H28 lands. Local/vendor checks listed as LOCAL-ONLY/NOT RUNNABLE, never executed in PR gate.
  - Input: `tools/progress_report.py`, H41/l1l2_fixtures JSON, `tools/l3check.py --build-corpus --json` (post-H28), `tools/realcheck.py` classification; `.github/workflows/*`.
  - Done when: PR run uploads/prints progress including L1/L2 generated-fixture per-file/per-feature counts, L3 target counts with firmware-proof separated from synthetic/harness (rule 13, L3 fragment/L4-emu/M8/L5-bench mapping per AGENTS.md), and L4 (M8 full-system emulator) / L5 (car/bench) explicit manual status where recorded; local-only checks in a separate "not run in CI, vendor data required" section; EXP links one CI run and maps fields to H27 rule-13 table.
  - Stop: if cross-job artifact passing is unreliable, generate progress in jobs that have inputs and mark aggregation as a follow-up, but still publish per-level summaries.
  - Claims: C-3290–C-3299

- [ ] **H43 — L3 generated-fixture corpus and per-reader progress for "our data" (extends H28)**
  - Status: open · Owner: — · Critical: no
  - Depends: H28, H40, M9.12 and runnable M9 reader targets
  - Goal: report "L3 which readers ran on our data and with what result" for generated (not only synthetic/vendor) data, without counting blocked/unrunnable as passes.
  - Scope: small L3 corpus from H40 generated artifacts via l3_harness conventions where feasible; run only runnable/prechecked targets with honest corpus mapping. Report per target `ran_on_our_generated_data,status,synthetic,l3_claim,reason`; BLOCKED/NOT RUNNABLE explicit. No-vendor CI respects H28 policy.
  - Input: `tools/l3check.py`, `tools/l3_harness/targets.json`/corpus, H40 artifacts, H28, reader-coverage L3 rows.
  - Done when: `l3check`/documented mode reports classification for generated-fixture corpus entries (0 runnable firmware readers initially is honest); progress output distinguishes synthetic probe, vendor/factory, and generated-fixture corpora; EXP states which readers ran on our data with evidence.
  - Stop: if no existing target can consume generated artifacts without new firmware-reader work, record target/corpus rows with NOT RUNNABLE reasons and stop; do not synthesize firmware verdicts.
  - Claims: C-3300–C-3309

- [ ] **H44 — L5 bench/car readiness package validation in CI and local-only/vendor-image test registry**
  - Status: open · Owner: — · Critical: no
  - Depends: H29, H27, H25
  - Goal: (a) validate L5 bench/car (S0–S3, AGENTS.md 2026-11-09 mapping) readiness manifests/checklists/result templates in CI without executing hardware or bundling vendor images; (b) classify vendor-image checks (realcheck IMG256, golden ROOT, full 194 REFER001, real LEV3456R) as LOCAL_ONLY_VENDOR with fetch commands/image keys, never run/downloaded in PR CI.
  - Scope: validator/registry tools (`--selftest`, no vendor data) for H29 manifest schema and a committed no-vendor local-only registry; CI validates schemas/templates only and prints "local-only, not run" / "L5 bench readiness validated, bench not executed" (never car PASS).
  - Input: H29 bundle format, `docs/research/card-test-plan.md` S0–S3, H27 L5/manual contract, `tools/realcheck.py`, H16 `fetch_image.py` keys, H28 optional mode.
  - Done when: validators pass on synthetic positive/negative fixtures; CI output shows L5 readiness-checked and local-only sections; H27 can ingest manual-result template format; no default PR job downloads vendor images.
  - Stop: if H29 format undefined, deliver minimal schema proposal + synthetic fixture and block implementation details on H29 with `Unblock:`.
  - Claims: C-3310–C-3319

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
  - Blocker: no `RDSTM001` row field resolves to a road identity (gate 0 of 9 fields on the US sample); OSM extract verified but not correlated.
  - Unblock: M4.17 (road-number ground truth without OSM; a road key must come first)
  - Result: EXP-2026-11-08-M4.2-rdstm-link-attrs (negative gate, with controls; supersedes the 2026-11-05 blocked EXP; claims C-901–C-903)
  - Note: EXP-2026-11-05-M4.2-rdstm-link-attrs failed for lack of OSM access
    and of a row → coordinate mapping. M4.17 tries the same question without
    OSM.
  - Depends: M4.1, M4.16
  - Done when: attribute values correlate with ≥ 5 known roads (OSM tags)
    in an EXP table.
  - Claims: C-900–C-909

- [ ] **M4.3 — Turn restrictions and connectivity encoding**
  - Status: blocked · Owner: claude/m4.3-turn-restrictions · Critical: no
  - Blocker: `docs/format/` has no connectivity/regulation record layout; the tools_ze0 writer's `0xff` regulation words are unverified, and `rd_check` reads only section-2 kind 0x1046 (3 of 5 local tiles stop).
  - Unblock: M4.23 (blocked on M4.24–M4.26: part-b grammar, regulation-word test, firmware reader VAs / LEV3456R addressing).
  - Result: EXP-2026-11-08-M4.3-turn-restrictions; the OSM side decodes (`r120176` no_left_turn at a named four-way junction, `tools/imf_restrictions.py`), the tile side is not documented and not verified, so Done-when is not reached.
  - Depends: — (M4.1 helps)
  - Done when: one known restriction (OSM `restriction=*` at a named
    junction) is found and decoded.
  - Claims: C-910–C-919

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
  - Status: blocked · Owner: task/m4.8b-coord-py-real-pois · Critical: yes
  - Blocker: bit-packed POINT pages (`POINT002/008/029`, 5405 pages) remain
    undecoded; no 0..2047-class geographic sub-unit position field linkable to
    the 16 M4.8b reference POIs was found by structural probe
    (`poi_bitpack_probe`, raw-A pair 0/1796 in P01 shard), so local scale 1 vs 2
    is untestable and the "within a few metres"/local-scale done-when is unmet.
    Latitude-offset "other method" is a non-pinnable fit to Wikipedia centroids.
    Origin 52742 (longitude) remains supported (C-1902).
  - Unblock: decode bit-packed POINT page grammar and re-test for 0..2047-class
    geographic sub-unit coordinates on ≥ 10 refs, or obtain an independent
    firmware/entrance-point method that pins local scale/origin.
  - Result: EXP-2026-11-08-M4.8b-bitpack-avenues.md (C-2936–C-2939, negative for
    tested scope). Prior: EXP-2026-11-08-M4.8b-transform-proof.md (16 POIs,
    origin 52742 fits longitude, latitude bias +2.8 km unexplained);
    EXP-2026-11-08-M4.8d-subunit-field.md (zlib-framed name records/ADDRE
    negative, C-2930–C-2935).
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
  - Claims: C-1900–C-1909, C-2936–C-2939

- [x] **M4.8d — Sub-unit field for POI/ADDRE positions**
  - Status: done · Owner: task/m4.8d-subunit-field · Critical: no
  - Depends: —
  - Goal: find a sub-unit position field in `POINT`/`ADDRE` records (a
    `0..2047`-class local value) so M4.8b can test local scale 1 vs 2.
  - Done when: the field is decoded (or `UNKNOWN` with the method) and the
    local-scale test is in an EXP that re-opens M4.8b.
  - Result: EXP-2026-11-08-M4.8d-subunit-field.md. No 0..2047-class geographic
    sub-unit *position* field found in zlib-framed POINT name records (50k
    US+EU) or ADDRE: `(v6&0x7ff,v8)` are 11-bit 2047-class but not local
    positions (0/50k pair matches to `local(A)`, 41–681 km on 16 M4.8b refs);
    `v16/v20` discrete; no 11-bit bitfield match above noise; ADDRE XX/YY are
    0..255 (M4.19). `tools/poi_subunit.py` added. M4.8b re-opened (local scale
    still unanswered; bit-packed POINT pages out of scope).
  - Claims: C-2930–C-2935 (was C-1908–C-1909, overlap with M4.8b fixed by H24; C-2936–C-2939 used by M4.8b re-attempt)

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

- [x] **M4.12 — `COORD001`/`ZCODE`/`ICODE001` remaining fields**
  - Status: done · Owner: task/m4.12-coord-zcode-icode-fields · Critical: no
  - Depends: —
  - Goal: `COORD001` `level`, the `ZCODE` offset base, `ICODE001` trie roots.
  - Done when: each is decoded with a test, in `coord-zcode-icode.md`.
  - Claims: C-1000–C-1009
  - Result: COORD001 `level` = 48-bit region bitmask `M=(level_u32<<16)|pad_u16`, one-hot `0x400000000000>>(i-1)` for non-last, last `level_u32==guard` (EU 33/US 11, verified). ZCODE: form A (018/033) offset base = ADDRE `unaddr(rec_addr_enc@0x1012)`, trie `crec` @0x1100 halfword-indexed, 16B recs (ZCODE018 rec0 verified); form B (31 files) `>HHBBHI` dir+ladder, no uniform offset base (OBSERVED). ICODE001 ISO header `>HH(hw,countries)`, 7 EU + 2 US per-language country-chain root byte offsets located by chain tracing; root-pointer index table not found. `tools/coord_zcode_icode.py` (--selftest + --verify-*), EXP-2026-11-06-M4.12-coord-zcode-icode-fields, C-1000–C-1009.

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

- [ ] **M4.16 — Place `RDSTM001` rows on the map** (blocked: no join key)
  - Status: blocked · Owner: task/m4.16-rdstm-placement · Critical: yes
  - Depends: M4.15 (M4.8 helps)
  - Goal: a row → tile/mesh → coordinate link, which M4.2, M4.3 and M5.3 need.
  - Input: `ref`/`src`/`dst` values (M4.1), tile road records
    (`tools_ze0`, `harness.py`), `COORD001` mesh formula, `mesh_grid.py`.
  - Unblock: M4.16b (per-record field directory), or M4.16c (the `INTER`/`FRWAY`
    `ref` lead) if the directory does not resolve the join.
  - Blocker: M4.1 16-byte fields (`ref/src/dst/code`) give no segment-specific
    join (hits at chance vs dense lid space; `ref`∩parcel/AB=0; C-1810) and
    M4.15/M3.7 leave framing/TMC semantics undecoded. `INTER*` `ref` byte-pattern
    enrichment (real>>random) is an unverified lead (C-1811).
  - Result: EXP-2026-11-06-M4.16-rdstm-placement; `tools/rdstm_place.py` probe
    + selftest. Join key NOT identified; done-when not met (negative).
  - Claims: C-1810–C-1819

- [ ] **M4.16b — Decode RDSTM per-record field directory (C-884) and re-test placement**
  - Status: open · Owner: — · Critical: yes
  - Blocker (resolved, kept as note): M1.11c is done (`MOVT/SHAR/SHLD/SHAD` pinned, EXP-2026-11-08-M1.11c-sh4dis-opcodes), so the decoder gap is closed. Schema table `0x00d53500` is still undecoded; the join itself stays with M4.16d.
  - Re-opened (PO grooming 2026-11-09, rule 15): M1.11c merged; the original "lacks MOVT/SHAR/SHLD/SHAD" blocker no longer holds.
  - Result (negative, prior): EXP-2026-11-08-M4.16b-record-framing — gate passed (five functions plain in Navi.exe sec0; callees verified); walk not run; done-when not met.
  - Depends: M4.15
  - Precheck: `python3 tools/sh4dis.py IMG256 nk.exe --image-start 0x200200 --check-real` (or the M1.11c pinned window) confirms no `.word` gap at the M4.16b walk sites; `python3 tools/cerom.py --image-start 0x200200 IMG256 va2file 0x00d53500` resolves the schema-table location (or records it as compressed `.data`).
  - Goal: reproduce the per-record length/offset directory walk from bytes to recover true TMC field boundaries, then re-run `tools/rdstm_place.py` on decoded fields (location/area/front/rear/inter-section).
  - Scope: the C-884 directory walk (`0x003f56bc`, `0x003f5e10`, schema `0x00d53500`) on Navi.exe build A; ≥20 decoded records tested for placement. No RDSTM writer.
  - Done when: ≥20 decoded records map to tile/mesh/coordinates with a named join key and ~0 random-key control, or the mapping is proven impossible with method recorded.
  - Stop: if schema table `0x00d53500` is unreadable (compressed `.data`) or the walk cannot be reproduced with current inputs, set `blocked` naming that dependency and keep the negative result.
  - Claims: C-2300–C-2309 (was C-1840–C-1849, a collision with M5.1b)

- [x] **M1.11c — `sh4dis.py`: MOVT, SHAR, SHLD, SHAD opcodes**
  - Status: done · Owner: task/m1.11c-sh4dis-opcodes · Critical: no
  - Depends: M1.11 (done)
  - Goal: decode the dynamic and single-bit shift opcodes and `movt` that the
    RDSTM directory walk (`0x003f56bc`, `0x003f5e10`) uses, so an offline walk
    can be run faithfully (M4.16b unblock).
  - Done when: `sh4dis.py --selftest` pins the four encodings (`0x0n29`,
    `0x4n21`, `0x4n0d`, `0x4n0c`) and a real-image window shows no undecoded
    opcode at the five M4.16b addresses; EXP recorded.
  - Claims: C-2650–C-2652
  - Result: EXP-2026-11-08-M1.11c-sh4dis-opcodes — `sh4dis.py` decodes MOVT/SHAR/SHLD/SHAD (LE pinned); selftest pins the four encoding forms and the five M4.16b instruction words; Navi.exe IMG256 `--check-real` shows no `.word` at `0x003f52dc,0x003f56fe,0x003f5746,0x003f5e1a,0x003f5e1e` (`movt r0, shad r1,r3, shad r3,r2, movt r3, shar r2`). `0x014a@0x003f52e2` stays `.word` (out of scope). C-2302 decoder gap closed for these forms; M4.16b walk/join remain open.

- [ ] **M4.16c — Verify `INTER`/`FRWAY` `ref` lead as aligned records**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.16
  - Goal: test C-1811 as aligned u32 fields (not byte scan) in `INTER*`/
    `FRWAY*`, decode the mesh/link reference, and test `INTER→tile/mesh→
    coordinate` with random-key control.
  - Claims: C-2310–C-2319 (was C-1950–C-1959, already used by M2.13b)

- [ ] **M4.16d — TMC location→segment placement via `TFTBL`/`reception.dat`**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.16b, M4.7
  - Goal: if `RDSTM001` is TMC (C-882), test placement through the TMC
    location table chain rather than raw row bytes.
  - Claims: C-2320–C-2329 (was C-1960–C-1969, already used by M4.19)

- [x] **M4.17 — Link attributes without OSM: road numbers as ground truth**
  - Status: done · Owner: claude/m4.17-road-class · Critical: no
  - Result: EXP-2026-11-08-M4.17-road-class — 96 numbered LCTBL roads of 7 OSM classes (420 rows, EU 2011 and 2014) with a street control; no record field beats its shuffled-road null under leave-one-road-out. Road-class field NOT established; `class_code` is a hypothesis (C-1825). The LCTBL road key does not reach RDSTM rows (C-1826).
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

- [ ] **M4.22 — Identity codes: header `0x180`, `DRSTR` `0x18c`, `BICON001` version**
  - Status: blocked · Owner: claude/m4.22-identity-codes · Critical: no
  - Depends: —
  - Goal: three identity fields are still unexplained and a generated card
    copies them blind: the six words at common-header `0x180`, the
    per-language list at `DRSTR001` `0x18c`, and `BICON001`'s data version
    `11/04/08/01` (every other map file differs).
  - Input: `tools/header_block.py`, `docs/format/file-header.md`, `drstr.md`,
    `assets.md`; the code table `05 04 02 07 0a 06 08 14`; EU 2011, US 2011 and
    2014/2016 images (`diff_years.py`); EXP-2026-11-05-40, EXP-2026-11-05-03,
    EXP-2026-11-06-H6.
  - Done when: `file-header.md` gives each field's meaning or `UNKNOWN` with
    the mutation that would settle it, the language codes are matched to the
    `SPEECH/` language sets, and `header_block.py check` runs on the four real
    samples; `drstr.md`/`assets.md` updated in the same commit.
  - Claims: C-2490–C-2499
  - Blocker: the `0x18c` codes have no code→language anchor in the four images (only counts agree: US 2/2, EU 8 vs 7 and 17 vs 16); `DRSTR001` `0x18c` is a node listing offset, not a language list (C-2493). The header fixes and the BICON001 retraction are done. See EXP-2026-11-08-M4.22-identity-codes.
  - Unblock: new task needed (none on the board yet): decode the `0x18c` code table from the ICODE001 per-language index (M4.12 left its root-pointer table unfound) or a firmware language table; OQ-44.

- [ ] **M4.27 — Decode bit-packed / non-zlib `POINT` pages**
  - Status: blocked · Owner: task/m4.27-bitpacked-point-pages-r2 · Critical: no
  - Depends: — (M3.11b, M4.8b)
  - Goal: M4.8b counted 16 POIs from inflated (`78 9c`) POINT streams; bit-packed
    (non-zlib) pages were not counted. Decode them so POI position checks and
    later writers cover the full set, not only inflated pages.
  - Precheck: `python3 tools/poi_point_check.py --selftest` and confirm the
    tool skips non-`78 9c` streams (the gap M4.8b reported).
  - Scope: `REFER001/POINT0nn` bit-packed pages on EU and US 2011; page decode
    only, no writer.
  - Done when: the bit-packed page layout is decoded (or shown to match the
    inflated record grammar with a different container) and `poi_point_check`
    (or a new tool) covers those pages, with counts in the EXP; or the EXP
    shows they carry no coordinate-bearing records with a control.
  - Stop: if the container is not zlib and not the known record grammar, record
    the header bytes and stop — do not guess the layout.
  - Claims: C-2670–C-2679
  - Blocker: done-when partially met — dominant non-`0x60|0x68` zlib inner pages decoded as phone/contact records (US 16B `w0=8,w1=6`, EU 20B `w0=10,w1=8`) carrying no coordinate-bearing POI positions, with counts/tool/controls (C-2670–C-2671); but index (`w0=1`/`w0=28`), mixed (`w0=2`), rare unknown classes, and 72.2% non-zlib raw POINT `.DAT` payload regions remain undecoded for potential indirect coordinate content (header bytes recorded, stop condition). A wider POI *position* sample is not enabled. M3.11b/M4.8b deps remain blocked.
  - Unblock: decode `w0=1`/`w0=28` index and `w0=2`/rare-unknown semantics (or prove non-coordinate with a stronger control) and/or characterize non-zlib raw payload POI-position storage; if a coordinate-bearing grammar is found, extend `poi_point_check` with counts to enable wider position sample (relevant to M4.8b/M4.28). Dep context: M3.11b, M4.8b.
  - Result: EXP-2026-11-08-M4.27-bitpacked-point-pages-r2.md (partial/blocked). Precheck: `poi_point_check` counts only `0x60|0x68` records; POINT002 2k–400k zlib sub-streams all `789c` (2543); gap = non-name zlib inner pages + 72.2% non-zlib raw payload. `tools/point_bitpack_decode.py` (+`--selftest`) classifies/counts bit pages: POINT002 747 name/1796 bit (1598 phone-us-fixed16 coord=no), POINT008 1359/3163 (2956 phone-us-fixed16), POINT029 208/446 (249 phone-intl-fixed20). Phone pages decode to ASCII numbers; heuristic coord-like scan 0/50 sampled phone and 0/50 unknown. Index/mixed/rare/unknown + raw regions not fully decoded (headers/counts recorded). `python3 tools/claims_check.py` OK; `tools/selftest.py --only poi_point_check --only poi_bitpack_probe --only point_bitpack_decode` OK.

- [ ] **M4.28 — Explain the POI latitude residual (+2.8 km) on a known entrance**
  - Status: blocked · Owner: task/m4.28-poi-lat-residual-r2 · Critical: no
  - Blocker: M4.27 (bit-packed POINT wider sample) unavailable in this session; M4.28 precheck not satisfied on M4.8b's 16 inflated-stream POIs — no POI with a reliably known, checkable entrance-vs-centroid/reference coordinate separation from allowed non-OSM sources identified (airports share ARP ref; building landmarks have sub-packed-unit separation, too small for the km-scale residual). Stop triggered; H1/H2 untestable. Analysis narrows C-1903 (dlat 132–6401 m, 48×, not a uniform fixed offset) but C-1904 not confirmed/narrowed-to-verdict/retracted.
  - Unblock: M4.27 (wider bit-packed POI sample) and/or identification of ≥ 3 POIs with citable entrance and centroid/reference coordinates from allowed non-OSM sources and a checkable separation; re-run precheck and complete the entrance/centroid/neither test, then update C-1904.
  - Depends: M4.27 (wider sample helps), M4.8d (sub-unit field)
  - Goal: M4.8b found a +2.8 km latitude bias (median 3.6 km total error, 16
    POIs) and could not separate transform error from "POI stored at a street/
    entrance point, not the building centre". Test on a POI whose true entrance
    is independently known.
  - Precheck: pick ≥ 3 POIs where the building centroid and the public entrance
    differ by a known, checkable amount (cite the source; no OSM).
  - Scope: coordinate residuals only; does not change `coord.py` constants
    without evidence.
  - Done when: the EXP states whether the residual tracks the entrance, the
    centroid, or neither, and updates C-1904's interpretation (confirm, narrow,
    or retract the bias hypothesis) with the evidence.
  - Stop: if no POI with a reliably known entrance can be identified from
    allowed sources, record the gap and stop.
  - Claims: C-2680–C-2689
  - Result: EXP-2026-11-08-M4.28-poi-lat-residual-r2.md (blocked). M4.27 unavailable; M4.8d done (C-2930–2935). Precheck/Stop on 16 M4.8b POIs (0/16 with citable entrance-vs-centroid coords from allowed non-OSM sources). dlat variance 132–6401 m (48×) argues against a single fixed-lat offset; C-1904 unresolved. C-2680–C-2682 added.

- [ ] **M4.29 — `class_code` second-country / non-motorway control (M4.17 follow-up)**
  - Status: blocked · Owner: task/m4.29-classcode-control-r2 · Critical: no
  - Blocker: second-country (US) `LCTBL001` exists (157,218 numbered, Georgia-area I-/US- refs) but no US OSM IMF/PBF with `ref`+`highway` is present in accessible archive (`leafre-work/osm/` Dolnośląskie-only), so M4.17 road-number→OSM-ref join/LORO vs null for a true second country cannot be computed (Stop condition triggered for that part). Non-motorway control was computed.
  - Unblock: produce/obtain a US (or other second-country) IMF/PBF matching the US card's coverage and run `road_class_probe.py` for true second-country LORO vs null; then re-open M4.29.
  - Depends: M4.17 (done)
  - Goal: M4.17 found class-pure `class_code` values (motorway codes recurring
    EU 2011/2014) but LORO failed over all joined rows, so `class_code` is a
    hypothesis (C-1825), not a road-class field. Test it on a second country and
    a non-motorway control set before it becomes a claim about classes.
  - Precheck: a numbered-road sample from a non-EU-2011 country present in the
    archive images (e.g. US), with the same road-number join M4.17 used.
  - Scope: `LCTBL001` `class_code` only; no RDSTM row correlation.
  - Done when: the EXP reports LORO vs null on the second country and on a
    non-motorway control; C-1825 is promoted, narrowed, or retracted with the
    new counts.
  - Stop: if no second-country numbered-road sample can be joined, record why
    and stop.
  - Claims: C-2700–C-2709
  - Result: EXP-2026-11-08-M4.29-classcode-control-r2 (blocked). Non-motorway control reported on EU 2011/2014/2016 Dolnośląskie joins (6 scopes): no scope reaches M4.17's 3 sd LORO-vs-null falsifier (EU 2011 below null; EU 2014/2016 < 1 sd above). EU 2016 replication also negative (+0.13 sd). US LCTBL sampled (157k numbered, 0x4e8f-dominant distribution) but second-country LORO not computable — no US IMF in archive. C-1825 narrowed (remains HYPOTHESIS), not promoted/retracted on a true second-country class-label join.

- [ ] **M4.35 — `class_code` hypothesis: second-country or firmware-reader deepening**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M4.29
  - Goal: test M4.17's `class_code` hypothesis (class-pure codes in-sample, LORO fails globally) with evidence that can separate "road class code" from "numbering/page/region code".
  - Precheck: reproduce M4.17 Table B / M4.29 control counts on the pinned EU sample with the committed tools (`python3 tools/road_class_probe.py --selftest` passes); identify one concrete second-country or non-motorway control sample available per rule 11/12.
  - Scope: offline analysis only. Either (a) a second country/control set with OSM refs, or (b) firmware-side evidence for the `class_code` field reader if a VA is locatable without guessing. No RDSTM writer, no L4.
  - Input: EXP-2026-11-08-M4.17, EXP-2026-11-08-M4.29-r2, `tools/road_class_probe.py`, `tools/lctbl_records.py`, `docs/format/rdstm.md`; M4.17/M4.29 follow-up notes.
  - Done when: EXP reports whether the pure `class_code` values recur for the same semantic class in the control sample (with counts and a negative control), or locates/denies a firmware reader path with VAs/evidence; updates claims as `HYPOTHESIS`/`OBSERVED`/`RETRACTED` only with reproducible commands.
  - Stop: after two control samples or two signature families fail to separate class from identity/region, record the negative and stop; do not promote `class_code` to a class mapping.
  - Claims: C-3200–C-3209

- [ ] **M4.31 — RDSTM link-class hints from pure `LCTBL001` class codes and link attributes**
  - Status: blocked · Owner: task/m4.31-rdstm-link-class-hints · Critical: no
  - Blocker: no stable join key between `LCTBL001` records and RDSTM/routing links on available samples (LCTBL has no coord/country/mesh/parcel/link id; tile sec2 entries have no LCTBL ref; RDSTM001 C-884 TMC framing not reproduced offline, C-2304, and RDSTM001 is TMC not routing links, C-887).
  - Unblock: M4.16b/C-884 (offline RDSTM001 TMC extraction for a TMC-side record join) or a new scoped task establishing a decoded, stable LCTBL↔MAPAL tile sec2 routing-link identifier (footer/attrs/page join) with controls.
  - Result: EXP-2026-11-08-M4.31-rdstm-link-class-hints (negative/Stop; M4.17 Table B precheck reproduced; join-key candidates tested with controls; bounded within-LCTBL record-identity test shows attr/footer co-variation but not a routing-link attribute or generator hint). Claims C-2970–C-2979.
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
  - Claims: C-2970–C-2979

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

- [x] **M5.1b — Ingest the real Dolnośląskie extract**
  - Status: done · Owner: claude/m5.1b-osm-pbf · Critical: yes · **Runner: non-Claude** (needs OSM, rule 12)
  - Input: `https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf`.
  - Depends: M5.1
  - Done when: IMF for the region passes `imf_check.py`; extract date,
    URL and SHA-256 recorded; counts of ways/nodes per `highway=*` in the EXP.
  - Result: region IMF (2,915,802 nodes, 362,811 ways) passes `imf_check.py`
    with 0 errors; date, URL and SHA-256 and per-`highway` counts in
    EXP-2026-11-08-M5.1b-osm-pbf.
  - Claims: C-2340–C-2349 (was C-1840–C-1849, a collision with M4.16b)

- [x] **M5.1c — OSM node tags: POIs, addresses and places into IMF**
  - Status: done · Owner: claude/m5.1c-osm-poi · Critical: yes
  - Depends: M5.1
  - Goal: the compiler can build roads only. A card also needs `POINT` POIs,
    `ADDRE` addresses and place names, and none of them has an IMF
    representation (EXP-2026-11-06-M5.1 follow-up).
  - Input: `tools/osm_ingest.py` (ways only), `docs/research/intermediate-format.md`,
    `imf_check.py`; the tag sets implied by `refer.md` POINT/ADDRE and by
    M3.9's name caps (32/64/128 chars, CP1252); a synthetic fixture with
    `place=*`, `amenity=*`, `addr:*` and one Polish name with diacritics.
  - Done when: `osm_ingest.py` emits POI/address/place records with the fields
    the writers need, `imf_check.py --strict` validates them, the diacritic
    round-trip is tested, and the record counts for a synthetic extract are in
    the EXP. The region run stays M5.1b.
  - Claims: C-2450–C-2459
  - Result: EXP-2026-11-08-M5.1c-osm-poi (C-2450–C-2458): `osm_ingest.py` reads node tags (XML, plain and dense PBF) and keeps POI, address and place nodes; the synthetic fixture gives 17 nodes, 3 POIs, 3 addresses, 1 place, identical bytes in 3 encodings; `imf_check --strict` (W007–W010); CP1252 fold in `imf_check.fold_cp1252`. Region counts stay open in M5.1b (C-2458).

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

- [x] **M5.4 — Tile writer: roads only**
  - Status: done · Owner: claude/m5.4-tile-splice · Critical: yes
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
  - Result: `tools/tilewriter.py` splices real OSM roads into the EU 2011 factory tile
    `B48R058R` (one 0x2046 directory, 18 parcels, 50,470 points decoded exactly); L2
    passes on the card tree with DRSTR rebuilt, and the L2 pass is structural only
    (EXP-2026-11-08-M5.4-tile-splice). Provisional classes; not firmware-tested.
  - Claims: C-1060–C-1069

- [ ] **M5.5 — Connectivity across tile borders**
  - Status: open · Owner: — · Critical: no
  - Depends: M5.4, M4.3
  - Claims: C-1070–C-1079

- [x] **M5.6 — Rebuild `DRSTR001`/`MMAIN001`/`.ind`/`CMP.LST`**
  - Status: done · Owner: task/m5.6-rebuild-drstr-mmain-ind-cmplst · Critical: yes
  - Depends: M5.4, M4.5 (M3.8: a verbatim `MMAIN001` copy is enough for the
    mount; the firmware checks only the 4096-byte length — EXP-2026-11-06-M3.8)
  - Input: copy `MMAIN001.DAT` verbatim when the tile set is unchanged; if
    tiles change, regenerate the `0x1ac` totals (C-164, big-endian) with
    `tools_ze0/make_mmain.py`, because `cardcheck` enforces the sum even
    though the firmware read path does not. Keep the file big-endian (C-1788).
  - Done when: L1 passes on the output card tree.
  - Claims: C-1080–C-1089
  - Result: `tools/rebuild_manifests.py` rebuilds DRSTR (`drstr_ze0.build`),
    MMAIN `0x1ac` tile-sum totals (big-endian), REFER001 `.ind` stream-preserving,
    and `CMP.LST`; synthetic selftest shows broken→fixed→L1 pass→idempotent
    (EXP-2026-11-08-M5.6-rebuild-manifests, C-1080–C-1084). Full extracted
    vendor-root L1 pass not re-run locally (no extracted root available).

- [x] **M5.7 — Street names into the name sections**
  - Status: done · Owner: task/m5.7-street-names-sections · Critical: no
  - Depends: M4.7, M5.4
  - Goal: write OSM street names into tile road-shape `name_off` values and the
    odd partner (background) record's names section, extending the M5.4
    factory-splice path.
  - Done when: `tilewriter.py` writes resolvable `name_off` + partner names
    section for named roads (synthetic factory selftest, positive/negative
    controls); `selftest.py --only tilewriter` and `claims_check.py` pass.
    Real-tile L2 with names not run in this worktree (no EU image present);
    firmware acceptance remains open (rule 13).
  - Result: `tools/tilewriter.py` takes IMF `name` (tag/record) as `1=NAME`
    labels, sets per-shape `name_off` (word 4), builds `fa_encode.names_section`
    and merges it into the odd partner background pair (`2*col+1`, `clarion_bg`
    w11/w12, strict rebuild) during 0x2046 factory splices; clipped named
    fragments keep the label; `--no-names` preserves old behavior; synthetic
    selftest 68/68, `selftest.py --only tilewriter` PASS, `claims_check.py` OK.
    (EXP-2026-11-08-M5.7-street-names-sections, C-1090–C-1092). Real-tile named
    L2/follow-ups open (C-1092).
  - Claims: C-1090–C-1099

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
  - Claims: C-2330–C-2339 (was C-1970–C-1979, already used by H9)

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

- [x] **M5.13 — Patch a file in place inside a factory image (`tools/imgpatch.py`)**
  - Status: done (tool; the real S1/S2 images are **M5.13b**, C-2027
    `UNKNOWN`) · Owner: session-ZMxuBT · Critical: yes
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
  - Result: EXP-2026-11-06-M5.13-imgpatch.md (`e4aa139`); `tools/imgpatch.py` patches files in place in factory images (cluster-chain/FAT/dir-entry). Real US S1/S2 images are M5.13b (`88332de`, EXP-2026-11-08-M5.13b-us-s1-s2.md).

- [x] **M5.13b — Build the real S1 and S2 US images with `imgpatch.py`**
  - Status: done · Owner: claude/m5.13b-us-images · Critical: yes
  - Depends: — (M5.13 tool and M5.12 edit are done; needs the US image)
  - Goal: the two cards the nearest milestone needs do not exist. C-2027 is
    `UNKNOWN` because `imgpatch.py` was only ever run on a synthetic fixture.
  - Input: `LEAF_2011-2012_US.img`, 7.5 G, sha256 `53342430…c5383`, from
    `https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img` (allowed host,
    rule 11; `tools/fetch_image.py` in H16 automates it); EXP-2026-11-06-
    M5.13 "Follow-ups" (the exact `imgpatch.py` command lines); the M5.12
    edited `POINT010` pair; `cmpind_writer.py` with **stock zlib 1.3.1**
    (`python3.13`, not zlib-ng — H9/`tools/zlibinfo.py`); `cardcheck.py --image`.
  - Done when: `us_S1.img` and `us_S2.img` exist with SHA-256 recorded and
    `cardcheck.py --image` PASS **with the volume label present** for each;
    every byte-diff range versus the factory image and versus S1 lies inside
    the replaced files' clusters or their 32-byte directory entries (listed in
    the EXP); the M5.12b control also runs — `mkcard.py` fresh build of the US
    tree reports the label with no warning; the commands are in the EXP so
    Marek can rebuild both images locally. Images stay outside the repo.
  - Claims: C-2350–C-2359
  - Result: EXP-2026-11-08-M5.13b-us-s1-s2. S1 is byte-identical to the factory US image; S2 passes cardcheck (label QSD-301-103); all 17,737 S2 diff ranges lie in POINT010 clusters or its directory entry; M5.12b fresh build PASS. Fixed an imgpatch EOC rewrite (C-2355). Recompression used zlib 1.3.2, not 1.3.1 (C-2354).

- [x] **M5.12b — `mkcard.py`: keep the volume label and factory root order on a fresh build**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: — (M5.13 is the path for the hardware cards; this is for M5.11)
  - Goal: a fresh build should not drop the root attr-`0x08` entry
    (`QSD-301-103` US, check the EU label) or reorder the root.
  - Input: `tools/mkcard.py` `build_fresh_partition`/`populate_dir`;
    `cardcheck.py` `_read_volume_label`.
  - Done when: the fresh build writes the source volume-label entry as root
    slot 0 and keeps the source directory order where names match; the
    self-test covers it; the M5.12 rebuild reports the label with no warning.
  - Claims: C-2030–C-2039
  - Result: EXP-2026-11-06-M5.12b-root-label.md (`9d37b5f`, `2fc7da7`); `mkcard.py` keeps root volume-label entry and source directory order on fresh builds; self-test/label warning covered per EXP.

- [ ] **M5.12c — Every copy of the renamed POI name on the US card**
  - Status: blocked · Owner: — · Critical: yes
  - Blocker: the uncompressed-files exact scan never finished, so the EXP has no list of every hit outside the compressed pages; the Done when is not met. `EXP-2026-11-08-M5.12c-poi-copies.md` still says `Status: done` in its header — reconcile it (M5.27).
  - Unblock: M5.27 (re-run the scan in EXP-2026-11-08-M5.12c-poi-copies Method 3, record hits, and reconcile EXP/TODO status).
  - Depends: — (M5.12)
  - Goal: tell Marek which screens should show `OSM2LEAF TEST POI1` (map
    label, POI list, name search) and whether any other file still holds the
    old name. **M3.12 removed the index risk**: `REFER001/INDEX003.DAT` does
    not exist on the EU 2011 or US 2011 image, so nothing there can shadow the
    rename.
  - Input: US tree; decompress all 58 `.cmp` pairs (`cmpind.py`) and scan them
    and every uncompressed file for `HANA HEALTH CENTER`, `HANA HEALTH` and the
    bytes that follow the name in record 0 of page `0x840ba0`; `LCTBL001`, the
    US-only `REFER001/INDEX001.DAT` (552448 B, M3.12) and the tile name
    sections.
  - Done when: the EXP lists every hit (file, logical offset, structure);
    if a search/sort index also holds the name, either extend the edit (new
    S2 via M5.13) or state what Marek should expect on screen.
  - Claims: C-2040–C-2049

- [x] **M5.14 — US geometry edit: move one road vertex (S3)**
  - Status: done · Owner: task/m5.14-us-geometry-vertex-s3 · Critical: yes
  - Depends: M5.13, M4.8c
  - Goal: the first geometry change Marek's unit renders, on the proven
    one-vertex path (M4.4: section 4 preserved, L2 pass on EU).
  - Input: US tree; `tools/tile_diff.py`, `section4.py preserve`, the M4.4
    mutate path, `coord.py` (M4.8c) to pick a recognisable road.
  - Done when: `tile_diff.py` shows only that vertex changed; the US tile
    checks pass (or the US-specific gap is named); M5.13 builds **S3**; the
    EXP names the road, tile and lat/lon before/after so Marek can find it.
  - Result: EXP-2026-11-08-M5.14-us-geometry-vertex-s3 (C-2050–C-2054). US tile
    `MAPAL001/B18R100R.DAT` (east Maui, B18R100R): sec1 L1 dir (30,65280) row 8
    k=17 layer 8 shape 1 vertex 2 moved (1851,52) 20.820312°N,155.796875°W →
    (1891,52) 20.924479°N,155.796875°W (+40, ~11.6 km N, coord.py scale 2
    hypothesis). `tile_diff` 1 changed/5729 same/0 moved; 117 B in 1 range; sec4
    byte-identical (484); `harness verify` 5730 ok, roundtrip OK; `imgpatch`
    built S3 `us_S3.img` `186f2ded…` (cardcheck PASS, check-diff confined to tile
    clusters+dir entry). Partner road name not resolved. Artifacts outside repo.
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

- [ ] **M5.16 — `LEV3456R.DAT` generator: levels 3–6 from OSM (H11 G4)**
  - Status: blocked · Owner: task/m5.16-lev3456-generator · Critical: no
  - Depends: M4.11, M5.4
  - Goal: `lev3456.py` re-encodes factory records byte-identically but nothing
    builds a level set from OSM, so a generated Poland card would show the
    factory coarse layers over the new roads.
  - Input: `tools/lev3456.py`, `map-tiles.md` §LEV3456R, EXP-2026-11-06-M4.11
    (level 5 62/62 decoded, levels 3/4 1,677/41 preserved), M4.11's open items
    (level-3 point index, the 2–6-word level-5 segment, background types),
    2014/2016 files as controls.
  - Done when: one level-3/4/5 set built from a mesh split of a synthetic
    extract is accepted by `lev3456.py verify` and (with M9.18) the firmware
    reader returns the same records; an unchanged input rebuilds
    byte-identically.
  - Claims: C-2400–C-2404 (C-2405–C-2409 reserved)
  - Blocker: M9.18 firmware-acceptance clause not verified (no LEV3456/section-4 L3 target). lev3456.verify acceptance and deterministic/byte-identical rebuild are proven.
  - Unblock: M9.18 (firmware reader verdict for generated L3/4/5).
  - Result: EXP-2026-11-08-M5.16-lev3456-generator. `tools/lev3456gen.py` (selftest OK, python3.13 stock zlib): generates L3/4/5 road records from mesh-split synthetic extract, template-splices EU 2011 LEV3456R; unchanged template round-trip byte-identical (76,066,304 B); generated L3/4/5 accepted by `lev3456.py verify` (exit 0, L5 strict 62/62 plain+stream, 0 opaque; L3/L4 best-effort matches factory preserved pattern); `generate()` deterministic. Not `[x]`: M9.18 firmware-reader clause unmet.

- [ ] **M5.17 — `LCTBL001.DAT` file builder (H11 G5)**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M5.18 — `POINT` and `ADDRE` writers, the two families Poland must generate (H11 G6)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.11, M3.13, M5.7, M5.1c (one PR per family: `[M5.18] POINT …`)
  - Goal: H11 G6, narrowed: `COORD001`/`ZCODE`/`ICODE001` for Poland already
    exist in the EU card and are copy-eligible (M3.17), so only the POI and
    address layers have to be generated.
  - Input: `refer.md` §POINT/§ADDRE, `mutate_refer_poi.py` (rename only),
    `addre.py` (grammar; `(XX,YY)` is not derivable 2D, C-1964), M4.9's open
    items (6-byte cell payload, `block>0` base, 22-byte index records),
    `INDEX003.DAT` (M3.12), `poi_icons.py` (34-row table; M4.10's open brand
    codes), the IMF output of M5.1c.
  - Done when: for each family a page/shard is built from IMF records, the
    firmware reader (M9.15) returns the expected name/coordinate, `l2check`
    passes on the rebuilt pair, and the `INDEX003` name-search entry either
    updates or is proven unnecessary.
  - Claims: C-2420–C-2429

- [ ] **M5.19 — `RDSTM001` writer (H11 G7)**
  - Status: open · Owner: — · Critical: no
  - Depends: M4.16b (record framing), M3.7
  - Goal: every `RDSTM001` row is copied verbatim from the factory card today;
    a Poland card needs rows that describe Polish segments.
  - Input: `rdstm.md` (twelve TMC fields with getters, C-882–C-889),
    `rdstm_record.py`, `rdstm_schema.py`, `0x003f61bc` field directory,
    EXP-2026-11-06-M4.16b.
  - Done when: a writer produces a file the firmware decoder walks with the
    expected values for ≥ 20 rows (an L3 target), or the EXP shows that
    copying is correct because the rows are region-independent.
  - Claims: C-2430–C-2439

- [x] **M5.20 — `mkcard.py --reconcile`: minimal-diff build for a changed tree**
  - Status: done · Owner: claude/m5.20-mkcard-reconcile · Critical: no
  - Depends: M5.13b
  - Goal: EXP-2026-11-06-M5.10 follow-up. `imgpatch.py` gives one-variable
    cards, but the compiler path still rebuilds the whole FAT, so a generated
    card differs from the factory in hundreds of ranges and one bad byte is
    invisible.
  - Input: `tools/mkcard.py` (`build_fresh_partition`, the M5.12b label/order
    preservation), `tools/imgpatch.py` (chain writer), `mkcard.diff_ranges`.
  - Done when: on the US and EU trees, a tree with one changed file yields an
    image whose diff against the factory lies only in that file's clusters and
    its directory entry (the property `imgpatch.py` gives), the unchanged-tree
    build stays byte-identical, and `--selftest` covers the reconcile path.
  - Claims: C-2460–C-2469
  - Result: EXP-2026-11-08-M5.20-mkcard-reconcile. Same-length changes on US and EU: one 16 B range, cardcheck PASS. Resize: 0 ranges outside the envelope, cardcheck PASS, but the DRSTR001.DAT value bytes are part of the diff (cardcheck requires them); the done status counts those bytes as the file's directory entry. Unchanged-tree copy on a real image not re-run (disk; C-1911 covers it). Fresh-build contrast not re-measured. Found and fixed the FAT NT case-flag gap (C-2466).

- [x] **M5.21 — Slot budget for generated pages: reject or re-pack, never overrun**
  - Status: done · Owner: claude/m5.21-slot-budget · Critical: yes
  - Result: EXP-2026-11-08-M5.21-slot-budget. `tools/slot_budget.py` (calibrate/build/verify, selftest 14/14). 4 % headroom (portability margin over the measured zlib-ng excess 3.64 %); US card: 19 pages fit with 13,749 names, 8,210 refused and listed, verify PASS, cardcheck PASS. 8,113 of 8,229 edited pages abut their neighbour, so more names need page relocation (separate task).
  - Depends: M5.13b (real-image batch path). M1.13 is **done**: stock zlib
    L6/memLevel 8 reproduces 471/471 factory `POINT001–009` pages
    (release-indistinguishable, C-2570), so the encoder is not the missing
    piece.
  - Goal: a generated page has a fixed slot (the factory stream, abutting the
    next page, C-2355 / M5.12c EXP). Edited content can compress worse than the
    original slot allows even with the factory-equivalent encoder (M5.12c: 5
    unfit edited pages). The compiler must know the slot before it writes, and
    either keep the page inside it with a stated headroom or refuse the page, so
    a card never gets a silent overrun or a broken neighbour.
  - Input: `tools/factory_zlib.py` (M1.13), `tools/mutate_refer_poi.py`
    (`refit_page`, `FitError`, the skip list in `*.skipped.json`),
    `tools/imgpatch.py`, the M5.12c EXP (**on branch
    `claude/m5.12c-poi-copies`, not yet merged**; slot rule: padding only over
    zero bytes; a stream may abut the next page), the M5.12c `plans.json`
    pattern. The slot rule will live in M5.12c's block C-2040–C-2049, **not**
    in C-2355 (that row is the imgpatch EOC fix).
  - Done when: (a) the compiler writes a per-page budget table (slot bytes,
    stream bytes, encoder used) and refuses a page whose stream exceeds
    its slot minus the headroom, with a `--selftest` on a synthetic abutting
    page; (b) on the US card, a generated edit set of at least 1000 POI names
    of mixed lengths either applies with every page inside its slot, or lists
    each refused page; no page is written past its slot (checked by
    `mkcard.diff_ranges` against the factory); (c) the EXP states the headroom
    chosen and the measured ratio that justifies it.
  - Stop: if no headroom keeps pages inside their slots on the real card, record
    the page-count and byte overflow in the EXP and set `blocked`: the next step
    is a page-relocation design (pointer tables), a separate task.
  - Claims: C-2580–C-2589

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

- [x] **M5.24 — `imgpatch` diff check: derive cluster ranges from BPB, not the write offset**
  - Status: done · Owner: task/m5.24-imgpatch-diff-bpb · Critical: no
  - Depends: M5.13b (done)
  - Goal: M5.13b's byte-diff check derived the cluster base from the `imgpatch`
    write offset, not from an independent BPB/FAT read. Harden the check so the
    "one variable" guarantee is verified against the filesystem's own layout.
  - Precheck: `python3 tools/imgpatch.py --selftest`.
  - Scope: the verification path in `imgpatch.py`/the M5.13b check script; no
    change to how bytes are written.
  - Done when: the diff-range check resolves each replaced file's clusters from
    an independent BPB+FAT read and reports a mismatch, and it still passes on
    the S1/S2 images (SHA-256s from M5.13b).
  - Stop: if the BPB read disagrees with the recorded S1/S2 ranges in a way
    that implies the earlier check was wrong, treat that as the finding (do not
    "fix" the result).
  - Claims: C-2830–C-2839 (was "next free block at claim time", fixed by H23)
  - Result: `tools/imgpatch.py --check-diff` resolves cluster/dir-entry ranges
    from an independent BPB+FAT read (not write offsets) and reports mismatches;
    selftest 59/59 OK; S2 vs factory (M5.13b SHA-256s) gives 17,737 ranges, 0
    outside, independently resolving cmp clusters 78193–78257/dir `0xb3bb7e80`
    and ind 78258/dir `0xb3bb7ee0`. EXP-2026-11-08-M5.24-imgpatch-diff-bpb.md,
    C-2830/C-2831.

- [ ] **M5.26 — Whole-POINT-pair regeneration for OSM name sets (beyond in-place slot budget)**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M5.27 — Finish M5.12c uncompressed-file scan and reconcile EXP/TODO status**
  - Status: open · Owner: — · Critical: no
  - Depends: M5.12c (blocked)
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

---

- [ ] **M5.28 — Provisional OSM→Clarion road class/speed table v0 (compiler-unblocking, L2-testable)**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M4.2 blocked; M4.17/M5.23 are inputs, not blockers)
  - Goal: unblock the OSM compiler spine with an explicit, versioned *provisional* mapping from OSM `highway=*` (+`maxspeed`/access where available) to Clarion tile class/style/speed values, so generated tiles can be built and validated at L1+L2 without claiming firmware acceptance (rule 13).
  - Precheck: `python3 tools/imf_check.py --selftest` passes; M5.4/M5.22/M5.23 writer/field behavior readable from `tools/tilewriter.py` and EXP-2026-11-08-M5.23; list in-scope `highway=*` values from Dolnośląskie IMF/profile if available.
  - Scope: data/tool file (name stated in PR, stdlib, `--selftest`) consumed by `tilewriter.py`/compiler; covers every in-scope `highway=*` or reports unmapped explicitly. No firmware claim; no M4.2 row key.
  - Input: M5.4 provisional-class behavior, M5.23 `(layer, cls_hi)`, M4.17 negative (class_code hypothesis), IMF highway tags.
  - Done when: every in-scope `highway=*` mapped or explicitly `UNMAPPED` (never silent drop); `--selftest` has positive and unknown-value cases; compiler records `mapping=provisional-v0`; one synthetic L2 tile build using the table passes existing tile checks; EXP states provisional/not firmware-confirmed and the M4.2/M5.3 gap.
  - Stop: if no safe Clarion value can be chosen without inventing semantics, use explicit `UNMAPPED` and refuse to generate that class until resolved.
  - Claims: C-3040–C-3049

- [ ] **M5.29 — Dolnośląskie one-tile pipeline: OSM→IMF→mesh→tile→L1+L2+gate report**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.1, M5.2, M5.4, M5.6, M5.10, M5.28
  - Goal: produce the first repeatable Poland compiler milestone: one OSM-generated tile swapped into a factory EU card, validated offline at L1+L2 with an explicit acceptance-gate report (operationalizes M5.11).
  - Precheck: `osm_ingest.py`, `mesh_split.py`, `tilewriter.py`, `rebuild_manifests.py`, `mkcard.py`/`imgpatch.py`, `cardcheck.py`, `l2check.py` selftests pass (record skips). Factory EU tile context obtainable (rule 11); use synthetic/small fixture if full extract unavailable.
  - Scope: script/pipeline (name stated in PR, stdlib + existing tools, `--selftest` on synthetic data) producing `out` where exactly one tile is OSM-generated (`mapping=provisional-v0`) and rest is factory/verbatim; rebuild manifests; run checks. No vendor bytes committed.
  - Input: compiler tools, `hddinfo.py`, M2.18 if landed, `profiles/dolnoslaskie-test.*`, reader-coverage matrix.
  - Done when: `cardcheck` and applicable `l2check` pass; report lists per gate (HDD_INFO/MAP CODE bytes, DRSTR/MMAIN/CMP.LST/.ind, tile round-trip/structure, section 4, manifests): `PASS`/`NOT-APPLICABLE`/`CANNOT-VERIFY-OFFLINE`/`NEEDS-L3`; EXP names tile, fixture SHA-256 or extract metadata, states provisional classes and firmware acceptance unknown (rule 13).
  - Stop: if required factory tile/tree cannot be obtained/fetched (rule 11), produce synthetic-only path and mark real-image run `blocked` with missing input named.
  - Claims: C-3050–C-3059

- [ ] **M5.30 — One-variable OSM tile card via `imgpatch`/reconcile (1:1 diff, L1+L2)**
  - Status: open · Owner: — · Critical: no
  - Depends: M5.29, M5.13 (imgpatch), M5.20 (reconcile)
  - Goal: make the Poland compiler candidate card differ from factory only in changed tile/manifests clusters and their directory entries (same safety pattern as S1/S2).
  - Precheck: `imgpatch.py` and `mkcard.py` selftests pass; M5.29 produces changed tile + rebuilt manifests with known paths.
  - Scope: apply M5.29 output via `imgpatch.py` (preferred) or `mkcard --reconcile`; run diff-range proof (every diff range inside replaced files' clusters or 32-byte dir entries). No hardware.
  - Input: factory EU 2011 image, M5.29 outputs, `imgpatch.py`, `mkcard.py`, `cardcheck.py --image`.
  - Done when: `cardcheck.py --image` passes; EXP lists every diff range confined to intended files' clusters/dir entries; manifests touched only when required listed explicitly. Images outside repo.
  - Stop: if changed tile/manifests cannot fit existing chains and relocate/reconcile widens diff beyond changed files, record ranges and stop — do not claim one-variable.
  - Claims: C-3060–C-3069

- [ ] **M5.31 — `mkcard --reconcile` resize: envelope contract, stale-tail policy, fresh-build contrast**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M5.20
  - Goal: make resize reconciles match the "minimal diff / one bad byte visible" intent that M5.20 met exactly only for same-length changes.
  - Scope: `tools/mkcard.py` reconcile path (`reconcile_partition`, `outside_ranges`, `_reconcile_drstr`) and its contract/reporting. Consider: (1) explicitly classify DRSTR index bytes in the reported envelope, (2) optional stale-tail preservation vs zero-fill with a documented tradeoff, (3) re-measure fresh-build contrast on the same changed trees (M5.20 did not). No format changes; no vendor data committed.
  - Input: EXP-2026-11-08-M5.20-mkcard-reconcile (C-2460–C-2469), `tools/mkcard.py`, `tools/imgpatch.py`, `tools/cardcheck.py`; US/EU same+grow cases reproducible from `tools/fetch_image.py` images when available.
  - Done when: on the M5.20 resize cases, the tool reports an envelope that is complete and understandable (DRSTR ranges named) and either preserves stale tail bytes with a tested option or documents why zero-fill is chosen; fresh-build contrast is measured (range count, not capped summary) for at least one same-length and one resize case on one image; `--selftest` covers the chosen behavior. EXP records real-image hashes/commands.
  - Stop: if preserving stale tail breaks `cardcheck` or FAT invariants, keep zero-fill, document the invariant, and make the envelope report prove all non-envelope bytes are unchanged.
  - Claims: C-3170–C-3179

- [ ] **M5.32 — Resolve M5.12c's 5 unfit POI pages with the M5.21 slot-budget strategy**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.21, M5.27
  - Goal: close the remaining 5 unfit POI pages from M5.12c (131/136 edited; 5 left per M5.12c S4) using a slot-safe strategy, now that M1.13 establishes stock zlib L6/m8 as the factory-equivalent encoder.
  - Precheck: reproduce the S4 unfit pages with `tools/mutate_refer_poi.py`/`tools/slot_budget.py` and stock zlib L6/m8; confirm M5.27 has reconciled M5.12c EXP/TODO status or record the dependency explicitly.
  - Scope: the 5 named pages/records only. Allowed outcomes: fit with a slot-safe repack/refit strategy that never overruns a neighbour, or explicitly refuse with measured slot/candidate sizes and a documented follow-up (page relocation/split). No silent overrun; no whole-POI-file rewrite unless every changed range is proven and cardcheck passes.
  - Input: EXP-2026-11-08-M5.12c-poi-copies, EXP-2026-11-08-M1.13-factory-encoder, EXP-2026-11-08-M5.21-slot-budget, `tools/slot_budget.py`, `tools/mutate_refer_poi.py`, `tools/factory_zlib.py`.
  - Done when: each of the 5 records is either edited on a `cardcheck`-passing image with diff ranges confined to the affected page/slot envelope (reported) or listed as refused with slot/candidate sizes and a concrete follow-up; EXP gives per-page before/after sizes and hashes.
  - Stop: if no slot-safe same-page strategy fits after the M5.21/M1.13 encoder search, stop with `blocked` or `open` follow-up for page relocation; do not pad over non-zero bytes or overwrite the next page.
  - Claims: C-3190–C-3199

## M6 — L5 bench/car: hardware and safety

No hardware is available now (L5). Planning tasks are open; tests wait. L4 (full-system emulator, M8) is the software integration path to prepare before L5.

- [ ] **M6.13 — Prepare the S3 bench package manifest (no hardware, no vendor bytes in repo)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.14 (S3 done), M5.24 (diff proof), M9.27
  - Pair: solo
  - Goal: make the S3 (LEV3456) bench run cheap when hardware returns: record artifact SHA-256/size/diff ranges, how it differs from S0/S1/S2 (one variable), which offline/L3 gates passed, and S3 pass/fail criteria. Image stays outside repo.
  - Precheck: `docs/research/card-test-plan.md` defines S3 criteria; M5.14/M5.24 EXPs name image/diff-ranges or package records `UNRECORDED`; `todo_check.py`/`claims_check.py` pass.
  - Scope: `docs/research/bench-packages/s3.md` (or a defined section in `bench-evidence-pack.md`) with manifest fields and reproducible hash/size verification commands outside repo. No flashing, no L5 claims.
  - Input: M5.14 EXP, M5.24 diff proof, M6.3/M6.7 plan, M9.27 matrix.
  - Done when: manifest lists artifact path placeholder + SHA-256 + size + diff ranges + base image identity, states "L5 NOT RUN", links pass/fail criteria; negative control: S2 manifest/criteria kept distinct (one variable).
  - Stop: if hash/diff ranges are not recoverable from recorded EXPs, record `UNRECORDED` and file follow-up; do not guess.
  - Claims: C-3230–C-3239

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
  - Unblock: build the `.uf2` locally (Pico SDK is not installable in the
    sandbox); that build is step 1 of M6.9 and needs a non-Claude runner.
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
  EXP-2026-11-06-M6.4). Status: blocked (hardware). Unblock: bench access
  (the first S0 run, M6.2). Claims: C-1930–C-1939
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

## M8 — L4 full-system emulation (QEMU `ze0` machine)

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

- [ ] **M8.A2 — Machine skeleton** `hw/sh4/ze0.c`: `sh7785`, RAM at phys
  `0x08000000` (128 MiB), P1/P2 aliases, unimplemented-device catch-all over
  `0xff800000`–`0xffffffff` and areas 4/6, `select SH4_CCN` with
  `sh4_ccn_iomem()` at `0xff000000` and `sh4_ccn_arrays()` at `0xf0000000`,
  and one `ze0-stubs` instance.
  - Status: blocked · Owner: task/m8.a2-machine-skeleton · Critical: yes
  - Depends: — (M8.A1, M8.A4 and M8.A5 are merged)
  - Note (PM 2026-11-06): the three series were never built together. M8.A1 saw
    `m8a4-0002/0003` rejected on 8.2.7; M8.A4/M8.A5 report them applying (the
    0003 banner says "Base: QEMU 8.2.7"). One clean `build.sh --force` over
    `patches/*.patch` settles it — record the resulting patch order.
  - Blocker (2026-11-08, this host): `glib2-devel`/glib-2.0 pkg-config missing
    and no prebuilt `qemu-system-sh4`; `build.sh --force` cannot
    configure/build, so `-M help`/`-M ze0` listing and `ce_qemu_probe.py`
    access-list reproduction were not run. Patch integration is verified:
    `LC_ALL=C sort` over all 5 `patches/*.patch` applies cleanly to pristine
    QEMU 8.2.7 (SHA-256 `1f0604f2…65b55`).
  - Unblock: run on a host with QEMU 8.2.7 `sh4-softmmu` build deps
    (glib-2.0 dev/pixman etc.) or a prebuilt LE `qemu-system-sh4`; execute
    `bash tools/qemu-ze0/build.sh --force`, record patch order + `-M help` and
    the `ce_qemu_probe.py`/`-M ze0` access-list comparison, update C-1240, and
    set this task `open`→`done` only if the done-when passes.
  - Done when: `bash tools/qemu-ze0/build.sh --force` applies every patch,
    builds, and `qemu-system-sh4 -M help` lists `ze0`; `-M ze0` reproduces the
    `ce_qemu_probe.py` access list; the run log and the final patch order are in
    the EXP.
  - Result: EXP-2026-11-08-M8.A2-machine-skeleton (blocked on build/runtime
    env; patch apply + 5-patch order verified, C-1240). Patch:
    `tools/qemu-ze0/patches/ze0-0001-hw-sh4-ze0-machine.patch`.
  - Claims: C-1240–C-1249

- [ ] **M8.A3 — Built-in loader** (`kernel=0x3e00200`, `app=0x200200`):
  parse `ECEC`/`ROMHDR`, copy B/C and A to `physfirst & 0x1fffffff`, PC =
  `nk.exe` entry. Done when booting needs no `-device loader`. Status: open
  · Depends: M8.A2. Claims: C-1250–C-1259
- [ ] **M8.A6 — Debug serial** (`sh_serial` at `0xffe46000`; writer
  `0x8804cfa4`, pointer at `0x8804ce78`). Done when the CE boot banner
  appears or an EXP shows why not. Status: open · Depends: M8.A2. Claims:
  C-1280–C-1289
- [ ] **M8.A8 — F0 EXP + register table** in `docs/format/firmware.md`.
  Depends: M8.A3…A6. Claims: C-1300–C-1309
- [ ] **M8.B1 — INTC model** (`0xff802000…`, `0xff804000…`, from
  `OEMInterrupt*` and the ISR at `VBR+0x600`). Done when a TMU0 interrupt is
  delivered and acknowledged. Depends: M8.A2. Claims: C-1310–C-1319
- [ ] **M8.B2 — TMU** (`0xffd80000`, `0xffd81000`, `hw/timer/sh_timer.c`).
  Done when `CurMSec` advances. Depends: M8.B1. Claims: C-1320–C-1329
- [ ] **M8.B3 — RTC/time** (`OEMGetRealTime`). Depends: M8.A2. Claims:
  C-1330–C-1339
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
  - Status: blocked · Owner: task/m8.e1-run-rom-decompressor-retry (retry 2026-11-08) · Critical: yes
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

- [x] **M8.E1b — Re-derive nk.exe ROM decompressor VA/prototype (M1.2c reverify)**
  - Status: done · Owner: task/m8.e1b-nk-decompressor-derive · Critical: yes
  - Depends: — (has IMG256; M1.2d framing known)
  - Goal: locate the real compressed-section loader/decompressor in nk.exe
    image B (IMG256, `--image-start 0x3e00200`) from actual bytes; correct
    M1.2c C-660–C-665.
  - Input: nk.exe sec0 (0x88001000, 0x4c800). Leads from M8.E1: 1 literal
    `0x00002000` at 0x88042298 (no PC-rel ref found); 5 `add #24,rN` o32-walk
    sites at 0x880128e4/0x88019b6c/0x8803a748/0x8803acbe/0x88047744; marker
    `0x8d80805b` bytes at 0x8804d786 (sec0 end, not code-referenced per M1.2c).
    Must handle M1.2a/M1.2d form 1/2 framing and LZXD-like `0x8d80805b` blocks.
  - Done when: verified VA+prototype recorded with capstone disassembly and a
    byte-level positive control (pattern found and reaches a decompressor call
    that takes src/psize/dest/vsize or equivalent); M1.2c EXP/claims
    retracted/corrected; M8.E1 unblocked.
  - Claims: C-2290–C-2299
  - Result: EXP-2026-11-06-M8.E1b-nk-decompressor-derive — M8.E1 refutation was a BE-vs-LE endianness artifact (C-1600/C-1603 superseded). **Verified (LE, IMG256 `92aa525d…`):** `fn 0x880385e4` o32 walk + `o32_flags & 0x2000` at `0x88038666`; compressed branch → `DECOMP_ALLOC 0x88034d94` then `DECOMP_WRAP 0x88037590(dataptr,psize,dest,vsize)`; chain `0x88037590`→`DECOMP_SECT 0x88037464`→`DECOMP_BLK 0x8803a384` (pool-confirmed). M1.2c C-660–C-663,C-665 restored (C-2290–C-2294). EXP-49 runtime decode not executed (needs `qemu-system-sh4` LE + DECOMP_WRAP kernel-context stubs, C-2294); M8.E1 unblocked (real VA/prototype known). Tools updated: `cedecomp.py`, `cedecomp_run.py`, README.

- [ ] **M8.E1c — QEMU slice for nk.exe decompressor oracle (compatible SH-4 map, DECOMP_SECT, EXP-49)**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (needs `qemu-system-sh4` LE with compatible memory map/`-M ze0` build deps or container; M8.A2 host deps may be missing)
  - Depends: M8.E1b, M1.2g (M8.A2 unblocks `-M ze0`; a documented compatible-map fallback may proceed in parallel)
  - Goal: execute a verified decompressor slice under QEMU and emit `decomp_oracle`-compatible results, so M1.2f gets runtime evidence (decoded length/hash for EXP-49, then Navi.exe sec1/sec2) without guessing the CE-LZXD block codec.
  - Precheck: `python3 tools/cedecomp_run.py --selftest` and `python3 tools/decomp_oracle.py --selftest` pass; `qemu-system-sh4` (LE) available and version recorded; IMG256 present/verified (rule 11). Record whether `-M ze0` is available or a compatible map is used (stock QEMU 11.1.3 `-M none` fails P1 0x88/0x8c access for nk.exe VAs).
  - Scope: `tools/cedecomp_run.py`/small helpers to run `probe` and `exp49` for `DECOMP_SECT 0x88037464` (preferred, C-2293) with a constructed input frame and minimal kernel-context/heap stubs sufficient for the section-decode path; output hashed decoded bytes as `decomp_oracle` JSON (no vendor bytes committed). Excludes full nk boot, F1, and 245/245 claims until produced.
  - Input: M8.E1b VAs (`DECOMP_WRAP/SECT/BLK/ALLOC`), `cedecomp.py`, EXP-49 vectors (`decomp_oracle.py`), `tools/qemu-ze0/` (`-M ze0` when built), `tools/ce_qemu_probe.py` patterns.
  - Done when: `cedecomp_run.py exp49 --image IMG256 --entry 0x88037464 --json <out>` (or documented equivalent) produces `decomp_oracle verify` PASS for EXP-49 sec1 (`0x484`) and sec2 (`0xcc0`) with recorded decoded SHA-256s in the EXP; `probe` still passes; negative control: wrong entry/garbled buffer does not verify.
  - Stop: if DECOMP_SECT requires kernel/global state not stubbable without F1/registry context, record faulting PC/register state and reduce scope to DECOMP_BLK sub-fragment under M9.29 or a narrower hook, with a follow-up; do not guess decoded bytes.
  - Claims: C-3260–C-3269

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
  - Claims: C-1680–C-1689

- [ ] **M9.10 — L3: decode the US POI with the firmware's own reader (software S2)**
  - Status: open (walk part runnable; name part waits for M3.11c) · Owner: — · Critical: yes
  - Note (2026-11-07): the old blocker ("walker in compressed sec1") was wrong
    (C-2128/C-2129). The walker `0x003f5194` already runs on the factory page
    via `tools/point_walk_l3.py walk` (C-2541). Port that into a
    `poi_record_walk` target now; add the name check when M3.11c names the
    accessor. Feed the page in the byte order M3.11b finds (until then:
    `swap16`, stated as an assumption).
  - Depends: M3.11c (name), M3.11b (byte order), M9.5 (M9.21 is done)
  - Precheck: `python3 tools/point_walk_l3.py walk` on the US factory
    `POINT010.DAT` page `0x840ba0` still reproduces C-2541 (exit 0, expected
    record count); `tools/l3_harness/runner.py selftest` and
    `targets.json` parse. Name accessor VA available only after M3.11c.
  - Goal: before any card goes into the car, run `Navi.exe`'s own `POINT`
    reader on the decoded factory page and on the renamed page, and read
    the name it returns. Pages are fed already decompressed (the `.cmp`
    layer is M9.11).
  - Scope: add/port `poi_record_decode` (or split walk/name) in
    `targets.json`/`runner.py`/`stubs.py`; run on factory and M5.12-mutated
    page `0x840ba0` with byte-order assumption stated; corpus outside repo
    (hashes only). No `.cmp` parsing here (M9.11).
  - Input: `tools/l3_harness/runner.py` + `stubs.py`; a new target
    `poi_record_decode` in `targets.json`; US `POINT010.DAT` page `0x840ba0`
    factory and after `mutate_refer_poi.py` (EXP-2026-11-06-M5.12, -H10).
    Corpus files stay outside the repo (hashes only).
  - Done when: `runner.py run poi_record_decode` returns
    `HANA HEALTH CENTER` for the factory page and `OSM2LEAF TEST POI1` for
    the renamed page, record 0, with the stub log in the EXP; plus one
    negative control (a corrupted `len2`) that the reader handles
    differently from the Python parser or the same way, recorded.
  - Stop: if M3.11c cannot name the accessor with a reproducible signature,
    record the walk-only verdict as partial, keep name check blocked on
    M3.11c, and do not invent an accessor VA.
  - Claims: C-2140–C-2149

- [ ] **M9.11 — L3: the firmware's chunk decoder on our recompressed `.cmp` (software S1)**
  - Status: blocked · Owner: claude/m9.11-chunk-decoder · Critical: yes
  - Unblock: M9.11b (runner entry kind that calls the firmware chunk reader; fills `cmp_ind_reader`).
  - Blocker: the firmware path passes on the factory, S1 and S2 pairs and on both controls (page `0x840ba0` byte-identical, corrupt `.ind` rejected, swapped `+4`/`+8` fails); `targets.json` `cmp_ind_reader` cannot be filled because `runner.py` has no firmware-call kind. The sec1 table that inflate reads (`0x574de0`, `inflate_mask[17]`) is supplied from public zlib source, see EXP.
  - Result: EXP-2026-11-08-M9.11-chunk-decoder (firmware path PASS; target registration open).
  - Depends: M9.5, M5.13b (the S1 pair). M3.2b is **no longer** a dependency.
  - Precheck: `python3 tools/chunk_decoder_l3.py` reproduces the firmware
    path verdicts from EXP-2026-11-08-M9.11-chunk-decoder on the
    factory/S1/S2 POINT010 pairs; `python3 tools/l3_harness/runner.py --help`
    confirms no firmware-call/memory-setup entry kind for `cmp_ind_reader`.
  - Goal: prove in software what S1 would prove in the car: the firmware's own
    zlib + chunk loop accept our recompressed bytes and return the same
    logical page. Re-scoped in the sixth pass: `fn 0x41c7e8` (M3.2b, C-2063)
    takes its 20-byte-stride chunk table from the caller, so the harness can
    build that table from `.ind` and never needs the `.ind` parser that lives
    in `Navi.exe` compressed sec1.
  - Scope: document the passing firmware path and controls; do not register
    `cmp_ind_reader` in `targets.json` until M9.11b adds the runner kind and
    a declared sec1-table input. No silent table default.
  - Input: `fn 0x41c7e8` (`@(28,ctx)` table; `+8` uncompressed offset, `+12`
    uncompressed length, `+16` compressed source, `+4` passed as r7), one-shot
    wrapper `0x542148`, `inflateInit2_ 0x542256`, `inflate 0x54233c`,
    `inflateEnd 0x54220c`; `runner.py` + `stubs.py`; the factory, S1 and S2
    `POINT010` pairs; `cmpind.py extract` as the reference page.
  - Done when: for all three pairs the firmware path returns page `0x840ba0`
    byte-identical to `cmpind.py extract`, one corrupt-`.ind` case is rejected,
    and one deliberately wrong table field (e.g. swapped `+4`/`+8`) is shown to
    fail — so the table layout is proven, not assumed. Fills the
    `cmp_ind_reader` target in `targets.json`.
  - Stop: if runner plumbing cannot expose the firmware-call kind without
    inventing sec1-table provenance, keep `cmp_ind_reader` blocked on M9.11b
    and record the gap (do not fake registration).
  - Claims: C-2150–C-2159

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

- [ ] **M9.12 — `l3check.py --card`: the software gate before any car test**
  - Status: blocked · Owner: task/m9.12-l3check-card-r2 · Critical: yes
  - Depends: M9.11 (runnable now), M9.10 (blocked — the first run reports the
    POI reader as "not yet available"), M9.6, M9.8 (tool skeleton)
  - Precheck: `python3 tools/l3check.py --help` and `--selftest` (if
    present) pass; at least M9.6 and the M9.11 firmware path are runnable as
    recorded in their EXPs. Factory/vendor image available per rule 11 for
    real `--card`/`--factory` checks.
  - Goal: one command that a card image must pass before Marek puts it in
    the unit: run every available L3 target (map-code compare M9.6, `.cmp`
    reader M9.11, POI reader M9.10, later tile reader) on the files that
    differ from the factory image.
  - Scope: extend `l3check.py` with `--card`/`--factory` diff selection and
    per-target pass/fail/not-yet-available reporting; call existing L3
    targets only. No car test, no format generation.
  - Done when: `l3check.py --card OUT.img --factory IMG` lists per target
    pass / fail / not-yet-available, exits non-zero on a fail, and the EXP
    shows it on S0 (all pass), S1 and S2.
  - Stop: if required card-diff inputs (S0/S1/S2 images) are unavailable on
    the runner and cannot be fetched/built by existing tools, report which
    corpora are missing and block that part rather than synthesizing a pass.
  - Blocker: `--card` is implemented and S2 (POINT010 diff vs US factory)
    reports `cmp_ind_reader` PASS via M9.11 firmware path
    (`chunk_decoder_l3.py`, byte-identical to `cmpind.decode`) with
    `poi_record_decode` honestly `not-yet-available` (M9.10), exit 0. S0/S1
    are byte-identical to factory so the diff-based gate finds no differing
    files (`NO_DIFFS`, exit 3, no fail) and cannot show runnable "all pass"
    verdicts until runnable targets can be evaluated on no-diff/baseline
    corpora or card-mode per-file wiring exists for registered targets.
    Done-when "S0/S1 all pass" not fully met.
  - Unblock: define/baseline no-diff handling or card-wire runnable targets
    (M9.11b `cmp_ind_reader` registration, M9.10 POI, M9.6 map-code) so S0/S1
    can produce runnable pass verdicts; then re-run and mark done.
  - Result: EXP-2026-11-08-M9.12-l3check-card.md (C-2160 tool/behavior).
  - Claims: C-2160–C-2169

- [ ] **M9.13 — L3 target `tile_reader` on factory and generated tiles**
  - Status: open · Owner: — · Critical: yes
  - Blocker (resolved, kept as note): M9.20 added module entry kind / `engine_hook`; the original "only synthetic/blocked entry kinds" blocker is gone.
  - Re-opened (PO grooming 2026-11-09, rule 15): M9.20 merged. Prior negative EXP: EXP-2026-11-08-M9.13-reader-run. Expect possible re-block on compressed sec1 `.data`, unmapped globals, or file I/O stubs (M1.2f/M9.24) — record faulting PC if so.
  - Depends: M9.5 (M3.5 reader VAs `0x0041f26c`/`0x004259bc`/`0x0042757a`; M3.6 helps)
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` passes with M9.20 module entry kind; M3.5 reader VAs resolvable via `cerom.py va2file`; compressed Navi.exe sec1/`.data` reader path accounted for (do not re-run as synthetic-only if firmware code/data path is unreachable).
  - Goal: run the real tile reader (M3.5) on one factory tile and on our round-tripped tile (M9.21) and compare the verdict.
  - Scope: register/repair a runnable `tile_reader` target once harness can call a module entry and required sec1/file I/O stubs exist; one factory and one round-tripped tile (M9.21). No new tile format claims.
  - Input: M9.21's round-tripped `B28R070R.DAT`; `runner.py run`, `stubs.py` (file I/O for `\SDMMC\MAPAL001\*.DAT`).
  - Done when: the reader returns a verdict for the factory tile and the same verdict (or a named, explained difference) for our tile.
  - Stop: if the reader path needs compressed sec1 data, unmapped globals, or file-I/O/import plumbing not yet modeled, block with the faulting PC/missing dependency and a new EXP — do not claim a reader verdict.
  - Claims: C-3250–C-3259 (PO grooming 2026-11-09; moved from C-2180–C-2189 to resolve overlap with M3.13)

- [ ] **M9.14 — L3 target `drstr_parser`**
  - Status: blocked · Owner: claude/m9.14-reopen · Critical: yes
  - Re-opened (ninth pass, rule 15): **M9.20 merged** (`562215a`) with the
    module entry kind and `engine_hook`, so the first blocker no longer holds.
    The reopened run (EXP-2026-11-08-M9.14-reopen) ran the module entry on the real head image:
    the reader's data is in compressed `sec1`, so it stops at once.
  - Depends: M3.10, M9.5 (both done)
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` and M9.20
    module-entry path pass; `python3 tools/cerom.py --image-start 0x200200
    IMG256` confirms `sub_00419350`/`sec1` layout; EU/US factory
    `DRSTR001.DAT` available per rule 11.
  - Goal: run the firmware `DRSTR001.DAT` parser as an L3 target and record
    whether it accepts factory/rebuilt card index files and rejects a
    corrupted case.
  - Scope: module entry for `sub_00419350` (and caller as needed) with
    coredll import binding/file stubs once unblocked; verdict map from
    observed return codes. No DRSTR format changes.
  - Done when: the firmware parser accepts the factory `DRSTR001.DAT` (EU and
    US) and one rebuilt by M5.6, and rejects one corrupted case, recorded.
  - Stop: if execution faults in compressed/unmapped `sec1` or needs coredll
    file/import behavior not yet stubbed, record the faulting PC and keep
    blocked on M1.2f/M9.24/M5.6 as applicable (do not guess verdicts).
  - Claims: C-2240–C-2249
  - Blocker: `sub_00419350` reads its coredll imports and buffer global from
    compressed `Navi.exe` `sec1` (UNMAPPED at `0x0055d8fc`); the Done-when also
    needs a DRSTR rebuilt by M5.6, which is open.
  - Unblock: M1.2f (decompress `sec1`), then M9.24 (import binding and coredll
    file stubs); the Done-when also waits on M5.6.
  - Result: EXP-2026-11-08-M9.14-reopen (negative, controls: M9.20 point-walker
    reproduced, compressed and outside-VA negatives; no DRSTR verdict; C-2240–C-2243).

- [ ] **M9.15 — L3 targets for `ADDRE`, `ZCODE`/`ICODE`/`COORD`, `LCTBL`**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.10 (pattern), and per family M3.13 / M3.14 / M3.15
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` passes; for
    the selected family, its M3 reader VA/signature is recorded with
    evidence and factory/edited records are obtainable per rule 11.
  - Goal: the same check as M9.10 for every other `REFER001` family; one PR
    per family (title `[M9.15] ADDRE …`), each updating its matrix row.
  - Scope: one REFER001 family per PR; add an L3 target/corpus row using the
    M9.10 pattern, compare firmware reader output to expected factory/edited
    values, update reader-coverage matrix row. No new family search in the
    same PR.
  - Done when: for each family the firmware reader returns the expected
    value for one factory record and one edited record.
  - Stop: if the family's reader VA or signature is not reproducibly located
    (M3 dependency not actually satisfied), record a narrow follow-up/blocker
    naming the missing evidence; do not guess the VA.
  - Claims: C-2250–C-2259

- [ ] **M9.16 — L3 map-load chain: open a whole card the way `Navi.exe` does**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.11, M9.13, M9.14 (M9.2 Ghidra helps to find the call order)
  - Precheck: component L3 targets for `.cmp`/DRSTR/tile/POINT path are
    runnable or explicitly reported not-yet-available by M9.12; factory US
    tree and S2 tree available per rule 11; COREDLL file I/O stubs exist
    or missing APIs are listed.
  - Goal: between single-function L3 and full-system emulation: call the
    firmware's own sequence (`HDD_INFO` → `DRSTR001` → `.cmp`/`.ind` →
    tile / `POINT` readers) against a virtual card tree, with COREDLL file
    I/O stubbed. This is the "mock `Navi.exe`" check of a generated card.
  - Scope: implement `runner.py chain --tree` over existing reader targets and
    file stubs; report per-step verdict/stub misses; integrate with M9.12
    when ready. No full-system emulation.
  - Done when: `runner.py chain --tree ROOT` runs the chain on the factory
    US tree without a stub miss, prints each step's verdict, and the EXP
    shows the same run on the S2 tree; `l3check.py --card` (M9.12) calls it.
  - Stop: if a component reader is blocked or call order cannot be derived
    without re-doing M9.2/Ghidra work, record the missing step and keep the
    chain partial rather than faking a pass.
  - Claims: C-2260–C-2269

- [ ] **M9.17 — L3 target `mmain_reader` (H11 G1)**
  - Status: blocked · Owner: claude/m9.17-reopen · Critical: no
  - Re-opened (ninth pass, rule 15): M9.20 merged (`562215a`); the module-VA
    entry it needs now exists.
  - Blocker: the M3.8 reader runs as a module entry (M9.20) but its first data access is at `0x0055d040`, in `Navi.exe` section 1 (compressed, `rw-`), which the map skips: `BLOCKED` UNMAPPED.
  - Unblock: M1.2f (port `DECOMP_BLK`, so section 1 can be mapped).
  - Result: EXP-2026-11-08-M9.17-reopen (negative: module run BLOCKED at a compressed `.data` access, controls PASS; C-2372–C-2373). Earlier block: EXP-2026-11-08-M9.17-m38-reader (C-2370–C-2371).
  - Depends: M9.5 (M3.8 located the reader)
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256`
    resolves reader `0x0041a438`/open/read VAs; `python3
    tools/l3_harness/runner.py --selftest` passes; EU/US factory
    `MMAIN001.DAT` (0x1000 bytes) available per rule 11.
  - Goal: `MMAIN001.DAT` is the only generated file whose reader is located
    and whose L3 target does not exist.
  - Scope: add `mmain_reader` in `targets.json`/corpus and run the M3.8
    module entry on factory and rebuilt 0x1000-byte files plus a 4095-byte
    negative; update matrix row 3. No format changes.
  - Input: reader `0x0041a438` (open `0x0041b780`, read `0x0041b954`, exactly
    `0x1000` bytes, no label/count check — C-1780–C-1789); the factory
    `MMAIN001.DAT` (EU and US); a `mmain_reader` entry in `targets.json` and a
    `corpus.py` row.
  - Done when: the target runs and returns the `0x1000`-byte read for the
    factory file and for a rebuilt one, rejects a 4095-byte file, and matrix
    row 3 carries the L3 result.
  - Stop: if execution faults in compressed/unmapped `sec1` `.data` (current
    blocker), record faulting PC and keep blocked on M1.2f; do not stub away
    the missing mapping.
  - Claims: C-2370–C-2379

- [ ] **M9.18 — L3 targets for `LEV3456R` and the tile sections (H11 G8)**
  - Status: open · Owner: — · Critical: no
  - Depends: M9.13 (matrix rows 18–20)
  - Precheck: M9.13 `tile_reader` pattern/runner path is available; VAs for
    `LEV3456R` load and section-4 consumer are evidenced; factory and
    generated tile/LEV3456R fixtures available per rule 11.
  - Goal: `tile_reader` covers `B28R070R` only; the coarse database and the
    section-4 consumer have no L3 target at all.
  - Scope: add L3 targets for coarse-level `LEV3456R` reader and section-4
    consumer on one factory and one generated case; compare to `lev3456.py`
    and `section4.py`; update rows 18–20. No format changes.
  - Input: the `LEV3456R` filename load `0x0040a014`, M3.6's section answers,
    `lev3456.py`, `section4.py`, `targets.json`, `corpus.py`.
  - Done when: the coarse-level reader and the section-4 consumer return the
    same records/name list as the Python tools for one factory tile and one
    generated tile, and rows 18–20 carry the verdicts.
  - Stop: if M9.13 is still blocked or the section consumer VA/signature
    cannot be stated reproducibly, record a narrow blocker/follow-up naming
    the missing VA; do not infer from Python output alone.
  - Claims: C-2440–C-2449

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


- [x] **M9.21 — `PySh4`: little-endian mode and `bt/s`/`bf/s`**
  - Status: done · Owner: claude/m9.21-pysh4-le · Critical: yes
  - Depends: —
  - Goal: the L3 interpreter can run `Navi.exe` code as it is in the ROM.
    Today `PySh4` fetches, loads and stores big-endian and rejects
    `bt/s`/`bf/s` (C-2546); `Navi.exe` is little-endian and uses `bf/s` in
    the POINT path (`0x3f39c0`, `0x3cd910`).
  - Precheck: `python3 tools/point_walk_l3.py walk …` passes with its local
    LE subclass (EXP-2026-11-07-M3.11-point-reader-2).
  - Scope: add little-endian fetch/load/store mode to `PySh4` with default
    unchanged, model `bt/s`/`bf/s` delay-slot behavior with self-test
    vectors, switch `point_walk_l3.py` to the shared engine, and verify the
    POINT path on the US page.
  - Input: `tools/l3_harness/engine.py` (`_load`/`_store`/`_fetch`,
    `cmp/str`, the `bt/s`/`bf/s` refusal), SH-4 manual for the delay-slot
    rule; `point_walk_l3.le_engine()` as the reference.
  - Done when: `PySh4(endian="little")` (default unchanged for the existing
    self-tests), `bt/s`/`bf/s` modelled with a self-test vector each,
    `point_walk_l3.py` uses it instead of its subclass, and `0x3f39c0` runs
    on the US page with the globals `0x00d5e4e4`/`0x00d5e4d0` set.
  - Stop: if delay-slot semantics or endianness could not be validated by a
    self-test vector against the SH-4 manual behavior, keep the change out
    and record the failing case.
  - Claims: C-2550–C-2559
  - Result: EXP-2026-11-08-M9.21-pysh4-le; `PySh4(endian="little")` and
    `bt/s`/`bf/s` in `tools/l3_harness/engine.py`; `0x3f39c0` runs on the US
    page with the globals set and matches `parse_page` (C-2550–C-2557).

- [ ] **M9.24 — Module entries that call coredll file APIs: bind imports, stub the CRT file calls**
  - Status: open · Owner: — · Critical: yes
  - Depends: M1.2f (`sec1` of `Navi.exe` must be decompressed first)
  - Precheck: `python3 tools/cerom.py` can resolve Navi.exe/coredll import
    context on IMG256 (recording the `exports coredll` KeyError if present);
    `python3 tools/l3_harness/runner.py --selftest` passes; EU factory
    `DRSTR001.DAT` available per rule 11. Re-derive coredll ordinals from
    M3.10 evidence before binding.
  - Goal: `runner.py` writes stub VAs into the module's COREDLL import slots
    (`0x0055d000`+ in `sec1`), models coredll `fopen`/`fread`/`fseek`/`ftell`/
    `ferror`/`clearerr`/`fclose`/`_modlu`/`wcstombs`/`strncat`, and models
    stack arguments for module entries, so `sub_00419350` (and its caller
    `0x00419684`, which reads above the stack top) runs on a file. Ordinals
    come from M3.10 and must be re-derived first (`cerom.py exports coredll`
    raises `KeyError` on this image). Input: EXP-2026-11-08-M9.14-reopen.
  - Scope: import-slot binding, CRT/file stubs, and stack-arg model needed
    for DRSTR/module-file callers in the L3 harness; verdict_map derived
    from observed return codes. No format claims; no sec1 decompression.
  - Done when: `runner.py run drstr_parser` on the EU factory `DRSTR001.DAT`
    returns a verdict or a named blocker with the faulting PC, and a
    `verdict_map` is written from the decoded return codes (not guessed).
  - Stop: if sec1 remains compressed/unmapped or coredll ordinals cannot be
    re-derived reproducibly, record the faulting PC/missing ordinal evidence
    and keep blocked on M1.2f/evidence; do not guess ordinals or verdicts.
  - Claims: C-2640–C-2649

- [ ] **M9.26 — Revisit `POINT` byte-order / source after M9.11b registers `cmp_ind_reader`**
  - Status: open · Owner: — · Critical: no
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

---

- [ ] **M9.28 — Module-entry input buffer/region mapping for real reader verdicts**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M9.20
  - Precheck: `python3 tools/l3_harness/selftest.py` and `python3 tools/l3_harness/runner.py selftest` pass; reproduce M9.20's real run showing the POINT walker stops at `UNMAPPED` on its page argument (`0x0`) rather than at decode/endian. Confirm M9.24 does not already provide a generic input-buffer mapping (it focuses on coredll CRT/import binding and stack args).
  - Scope: `tools/l3_harness/` module-entry path (`runner.py`/ROM map/corpus conventions). Add a way to map a caller-supplied input buffer or file-derived bytes at a chosen guest VA for module targets, with explicit bounds and provenance in results. No firmware format claims; no Ghidra/QEMU.
  - Goal: let module-entry reader targets (M9.13/M9.14/M9.17 class, and the M9.20 walker follow-up) receive real input instead of failing at argument-pointer loads, so verdicts are limited by mapped data/stubs rather than missing input plumbing.
  - Input: EXP-2026-11-08-M9.20-l3-plumbing (open question: input region), EXP-2026-11-08-M9.14-reopen, EXP-2026-11-08-M9.17-reopen, `tools/l3_harness/runner.py`, `tools/l3_harness/rommap.py`, `tools/l3_harness/corpus.py`, M9.24 task text.
  - Done when: a synthetic module-entry target reads from a mapped input buffer and returns a verdict; at least one existing reopened/blocked reader target can be re-run past the argument-pointer `UNMAPPED` fault or reports a new, more specific blocker (faulting PC + missing data/stub named). `--selftest` covers bounds/provenance; `tools/README.md` updated.
  - Stop: if the target's input source cannot be located or bounded from available evidence, add/require an input-source locating subtask and record the missing source; do not map guessed bytes and call them a reader verdict.
  - Claims: C-3210–C-3219

- [ ] **M9.29 — Ghidra headless micro-harness for decompressor sub-fragments (LE SH-4)**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (Ghidra 12.2+/JDK required; in-repo script/selftest runnable without Ghidra)
  - Depends: M1.2g, M8.E1b (M9.2 project import helps but is not required for a targeted function run)
  - Goal: test `DECOMP_SECT`/`DECOMP_BLK` and helper sub-fragments on controlled buffers in Ghidra headless/pyghidra, emitting `decomp_oracle`-compatible results. Complements QEMU (M8.E1c) and isolates CE-LZXD block-codec behavior.
  - Precheck: `python3 tools/decomp_oracle.py --selftest` passes; harness script has `--selftest`/`--plan` with no Ghidra/vendor data. With Ghidra: `analyzeHeadless` found and processor is **SH-4 little-endian** (not BE) per M1.11/M8.E1b/C-2290; `ghidra_import.py`/`l3_run.py` BE references are a hazard to fix/guard.
  - Scope: script under `tools/l3_harness/ghidra/` (name in PR) to load nk.exe image B at base, map src/dest/stack, call chosen VA (DECOMP_SECT/BLK/helper) with r4-r7/stack per prototype, read dest/len/r0, write JSON for `decomp_oracle verify`. No full-reader wiring, no 245-section claim without evidence, no default PR CI.
  - Input: M8.E1b VAs, IMG256 nk.exe mapping via `cerom.py`, `decomp_oracle.py`, `ghidra_import.py` patterns (LE-corrected).
  - Done when: `--plan` prints headless command/processor/VA/memory/expected output; `--selftest` validates plan/result shape without Ghidra; with Ghidra (EXP, non-Claude) EXP-49 sec1 or a pinned DECOMP_BLK sub-fragment yields `decomp_oracle verify` PASS or a faulting-PC negative EXP localizing the codec gap.
  - Stop: if controlled-memory execution is not feasible in the available Ghidra version, record limitation and use Ghidra decompilation/disassembly as evidence feeding M1.2f (not runtime proof) with a follow-up.
  - Claims: C-3150–C-3159

- [ ] **M9.30 — DECOMP_BLK sub-fragment map and test vectors (shift/LZXD-like, feeds M1.2f)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M8.E1b, M1.2g (M9.29 and M8.E1c provide runtime oracles when available)
  - Goal: break `DECOMP_BLK 0x8803a384` / `DECOMP_SECT 0x88037464` into testable sub-fragments (bit reader, shifts/masks, E8/`0x8d80805b` block handling, length/distance decode) with pinned inputs/expected outputs, so `sh4dis.py` shift-encoding gaps and the CE-LZXD codec are resolved against evidence.
  - Precheck: `python3 tools/sh4dis.py IMG256 nk.exe --image-start 0x3e00200 --va 0x8803a384 --count 20` (or helper VAs) decodes as far as supported; `python3 tools/decomp_oracle.py --selftest` passes. IMG256 per rule 11.
  - Scope: analysis + small committed test-vector fixtures (hex/JSON, no vendor blobs beyond short bytes/hashes/offsets) and `sh4dis.py`/helper extensions for blocking shift encodings (SHAD/SHLD/rotcl etc.) with selftests; runtime sub-fragment results from M8.E1c/M9.29 when run. No guessed full codec.
  - Input: M8.E1b chain, `tools/sh4dis.py`, `tools/cecompress.py`/LZXD refs (attribution/licence checked), `decomp_oracle.py`, EXP-49 block structure (M1.2a/M1.2d).
  - Done when: `sh4dis.py` decodes the blocking shift/bit instructions in DECOMP_BLK/SECT (listed before/after in EXP) with selftests; vector file has >=3 sub-fragment cases each runtime-verified by M8.E1c/M9.29 or marked `HYPOTHESIS` with disassembly evidence and falsifier; M1.2f can cite vectors.
  - Stop: if a CE-specific LZXD variant cannot be split without a running oracle, name the minimal reproducible fragment needing QEMU/Ghidra and keep pure-Python porting blocked on M8.E1c/M9.29.
  - Claims: C-3220–C-3229

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
| Building S1/S2 with `mkcard.py`'s fresh build | re-lays out the whole FAT and drops the root volume-label entry (200 diff ranges), so three variables change at once | M5.13 `imgpatch.py`, M5.13b |
| `NaviStateCC` vtable hunts (EXP-27…29) | parked; COM objects come from runtime or `DllGetClassObject` with real VAs | M9 / M8.E3 if needed |
