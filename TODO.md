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
   has the task ID in its title (`[M2.1] …`). Look at both right before
   claiming, after `git fetch origin`, on `origin/main` and the open PR list,
   never on a worktree's possibly stale copy of `TODO.md`.
3. **First commit: mark the task `in progress`.** Immediately after creating
   the branch/worktree (within a minute, before reading or planning), make a commit that changes **only** your
   task's line to `Status: in progress · Owner: <branch>` (subject
   `todo: start <ID>`; `python3 tools/board.py claim <ID> --owner <branch>`). **Push it at once** (`git push -u origin
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
   both sides of a conflict; never drop another task's lines. For the two
   board files use `python3 tools/board.py resolve <file>` (merge by ID), never
   a pasted copy, and check `python3 tools/board.py lost --base origin/main`
   exits 0 before the push (H123; PR #340 lost 42 tasks and 199 claim rows).
6. **Last commit: the work plus `done`.** Commit the actual work, and in the
   same commit set `Status: done`, tick `[x]` and add one line `Result:`
   naming the EXP (`python3 tools/board.py done <ID> --result "…"`) (subject in the normal style, e.g. `tools: …`). Run `python3 tools/selftest.py` (and the task's
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
   free ID of that stream, the full field set, and `Owner: —`
   (`tools/board.py next-id <stream>`, `next-claims`, `add-task <file>`; every
   edit of `TODO.md`/`claims.md` goes through `tools/board.py`, AGENTS.md). Before
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
    **The flag is a property of the runner, not of the task:** on a host with
    normal internet (verified 2026-11-17: `api.openstreetmap.org` 200,
    `download.geofabrik.de` 307, full EU card in `archive/sd-images/`), a
    `Runner: non-Claude` task runs normally — do not treat the flag as a
    blocker there, and do not re-add it to a task whose only need is network.

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
    - **"in compressed sec1" is not a blocker until `va_class.py` says
      `INIT` (PM twelfth pass, 2026-11-10, H49).** 94.5 % of the compressed
      bytes are BSS (zero at load) and `Navi.exe` sec1 starts with the 846-slot
      import table (C-3440–C-3442). Run `python3 tools/va_class.py IMG
      --module M --resolve-with 0x3e00200 VA`: `IAT` → bind a stub (M9.35),
      `BSS` → find the writer (M3.22 pattern), only `INIT` → M1.2f.
    - **`INIT` is readable, and a `fn` must be a function (PM thirteenth
      pass, 2026-11-11, H51).** `python3 tools/nk_decomp.py section IMG
      --module M --index N -o OUT` runs the kernel's own decompressor in
      PySh4 (245/245 sections). Before a VA is searched for, called in L3 or
      written into a doc as `fn`, run `python3 tools/nk_decomp.py pdata IMG
      --module Navi.exe VA`: `START` is an entry, `INSIDE` gives the true
      start (M3.2b lost two sessions to `0x0041c7e8`, which is 12 bytes into
      `fn 0x0041c7dc`), `GAP` is a leaf or data.
    - **Name the build (H51).** The EU and US cards carry different
      `Navi.exe` builds; a VA is valid for one of them. Write `EU2011` or
      `US2011` next to every VA and every L3 verdict (M1.22).

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

17. **Map first (PM, 2026-11-17, fourteenth pass).** Between 2026-11-11 and
    2026-11-17 the board closed 33 tasks: 22 housekeeping, 10 firmware
    tooling, 1 L3, none in M3/M4/M5 (EXP-2026-11-17-H101). Review roles found
    record defects faster than the TL closed them, and each defect became a
    task. From now on:
    - **Budget.** A TL batch holds at most one H task for every three tasks
      from M3/M4/M5/M9. If fewer than three map tasks qualify, the batch is
      smaller — never filled with H.
    - **A record defect is fixed where it is found.** SE and QA correct a
      wrong number, a dead command or a missing claim row in the same pass
      (one commit, the EXP and `claims.md` only). A new H task is allowed only
      when the defect is in a **tool** that a map task depends on, and it
      names that map task in `Depends`.
    - **One batch for the backlog.** H53–H100 that only repair a record or a
      gate are closed in one TL pass or dropped; they are not picked one per
      cycle.
    - **Progress is counted on the map.** Each PO pass reports four numbers
      before anything else: rows of `reader-coverage.md` with a located
      reader, rows with a running L3 target, bytes of a factory tile
      explained by `docs/format/` (sections 1/2/4), and the highest card
      ladder step (M5.38) that passes its gate. A cycle that moves none of
      them says so in its first line.
    - **Big research tasks are split before they are skipped.** If a
      critical task stays unowned for two cycles, the PO cuts a first slice
      that one pair can finish in one session and puts it first.

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
| `US256` (US firmware head, 256 MiB) | `python3 tools/fetch_image.py --image US256 -o PATH` (pinned, verified, H62; `--image US --part 256M` is the same pin) | `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da` |
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

## Priorities (PO grooming 2026-11-22, 23rd pass; `origin/main` `af469580`)

**This pass widened the board on Marek's request (2026-11-22): 120 tasks added
so that about 100 are takeable at once.** It is a deliberate exception to "at
most ~8 new tasks per pass". The four rule-17 numbers on this host
(`python3 tools/map_signals.py`, no factory tree on disk):
`readers: located 18 partial 1 unlocated 1` · `l3_rows: l3-running 8` ·
`tile_bytes: NOT RUN` · `card_step: NOT RUN`. The first two did not move since
the 22nd pass; the map did not move this pass either — the board did.

**What changed in the picture: L4 exists.** `-M ze0` mounts the card, runs
`Navi.exe` and draws a first screen (M8.C1b–C1e, M8.C1f in flight). So the
expensive car tests can be rehearsed in the emulator, and the firmware can be
asked which bytes it reads. Three new fronts follow from that:

1. **Emulator connectors (M8.H1–M8.H69)**, plan in
   [`docs/research/qemu-connectors.md`](docs/research/qemu-connectors.md):
   chips behind serial lines (GPS, display unit/touch, audio microcontroller,
   Bluetooth, VCAN) are Python *peers* on host sockets, not QEMU code, so many
   agents can work without patch conflicts. Critical first: **M8.H1** (serial
   lines as chardevs), **M8.H27** (GPS protocol), **M8.H36** (touch path),
   **M8.H43** (audio-microcontroller handshake), **M8.H8** (SD read trace →
   file/offset), **M8.H13** (`l4check.py`, the L4 gate).
2. **KIWI (M4.63–M4.78, M3.38, M3.39)**: Marek's lead that Clarion (ex-Xanavi,
   a KIWI-W member) stores maps in KIWI structures. The ROM names `Xanavi` and
   `MDP_*RcvParcel`. One task per structure, each with a byte test; **M4.69**
   (road frame) and **M4.72** (route planning) are critical because they would
   unblock the class table and the section-2 chain. **M4.78** writes the verdict.
3. **Acceptance in the emulator (M2.21–M2.24, M6.22, M6.23, M8.H64)**: card
   gates, the "in-place only" rule (**M2.22**) and the S1/S2 cards rehearsed at
   L4 before any car test.

**Map work that needs no emulator (take these first if you are not on M8):**
**M4.89** (Poland on the 2014/2016 cards as an answer sheet — also answers
M5.64), **M4.69**, **M4.72**, M4.79–M4.84 (claim-only decoders become tools),
M4.85 (EV layer), M4.86 (largest unexplained block of a tile), M4.87 (Polish
glyphs), M5.64, M5.65, M5.66, M5.76 (synthetic town, no network), M9.68.

**Rule 17 budget still holds:** a batch takes at most one M8.H task that is
pure tooling for every three tasks from M3/M4/M5/M9 or from the reader rows of
M8.H (`Step: reader`). Do not start a dependent M8.H task before its static
read is merged.

**In flight:** see the open draft PRs (`[ID]` titles); do not claim those IDs.

**For Marek:**

- **An OSM extract on `files.viaaq.eu`** (`dolnoslaskie-latest.osm.pbf`, then
  Poland) would let Claude agents run M5.61, M4.2, M5.3, M5.77 and M5.78, which
  today need a runner with open internet (`Runner: non-Claude`).
- **KIWI material**: a specification PDF or a lawfully held KIWI DVD image
  (`ALLDATA.KWI`) on `files.viaaq.eu` would turn M4.65 and M4.77 into Claude
  tasks and give the mapping a positive control.
- **Archive**: 81 done blocks moved to
  `docs/research/todo-history-2026-11-22.md` this pass; 32 more done blocks
  stay because they hold `fn 0x…` lines pinned by the `fn_audit` snapshots.

### By card-ladder step

The ladder ([content](docs/research/card-ladder.md), [gates](docs/format/card-ladder.md))
orders the map work; the live grouping is `python3 tools/card_ladder.py steps --check`
(`*` = critical, `(page)` = tag held in the page while the owner's PR is open).

- **P0 (built)** — container and `DRSTR001` parser accepted in L3 (M9.13, M9.14); QA pin **M5.40**; L3 gate **M9.60**.
- **P1 (display-only card, PR #423)** — **M9.58** (the renderer walks our record), **M5.61** (the 4 Poland tiles), **M9.61** (the same reads on the US build, split by M9.63); new **M5.66** gates a rendered tile at L2.
- **P2 (routing)** — **M4.55** (in flight) → **M4.40** → **M5.57** → **M9.56**; M4.23, M4.24, M4.3 → M5.5; **M9.18** → M5.16; **M5.3** (waits on M4.2); M4.56 (section 4, route guidance).
- **P3 (names)** — **M3.32** + **M3.36** (board truth) → **M3.30** → **M3.13** → **M4.36**; **M4.2**; **M9.15**; **M5.64** (real LCTBL table code); new **M5.65** (section-4 place names from OSM).
- **P4 (search)** — **M5.18** (POINT/ADDRE writers, waits on M3.13), **M5.32**, **M5.63** (POI position writer, PR #427); M9.10/M9.41 done.
- **tooling** — **M9.60** → **M5.35**; **M9.61** (split via M9.63); M9.59; M9.31 → **M9.12**; **M9.2** (Ghidra, needs a non-Claude runner). **M9.16** is split into M9.60 + M9.61.

### Critical path to "maps run in the car" (L1 → L2 → L3 → L4 → L5)

> Level mapping (2026-11-09): **L3** = firmware fragments, **L4** = full-system emulator (QEMU/M8), **L5** = bench/car (M6).

- **L1 (ready for real cards; fixture exists):** `cardcheck --image` plus the `imgpatch` diff gate the P0/P1 cards; `cardcheck --generate-fixture` builds a vendor-free tree (H40 done, H105 done). Open: **H41** → **H42** (CI use), **H104** (baseline).
- **L2 (the product path):** P0 built; P1 card **M5.61** (blocked, see its block). Open: **M5.35** (one command), **M5.66** (rendered tile as an L2 gate), **M5.76** (synthetic town so compiler tasks run without network) → **M7.1** (all Dolnośląskie).
- **L3 (moving):** container, record read and the renderer walk are done on a generated tile. Open: **M9.68** (which header fields the map client checks), **M9.15** and **M9.18** (targets per family), routing **M4.55** → **M4.40** → **M5.57** → **M9.56** (blocked chain; **M4.72** tests a KIWI shortcut), card gate **M9.31** → **M9.12**.
- **L4 (QEMU `-M ze0`):** **M8.H1** (serial chardevs, TX and RX), **M8.H27** (GPS frame grammar) and **M8.H30** (GPS peer) are done; **M8.H8** (SD block reads mapped to card files) completed. F3 reached (card mounts, M8.C1b), `Navi.exe` runs (M8.C1d), display engine handshake done (M8.C1e); **M8.C1f** (in flight) draws the screen. The one-command `tools/l4check.py` gate is available (factory card exit 0 stage F5). Next: **M8.H64** (P0 card at L4) → **M8.E4**; **M8.H9** (coverage) completes the format oracle; GPS **M8.H31**, touch **M8.H36/H38/H39** feed inputs through it. Card acceptance at L4: **M2.21**, **M2.22**.
- **L5 (bench/car, one variable per run):** hardware unavailable. Order when it returns: **M6.2** S0 → **M6.18** flash backup → **M6.5** S1 → **M6.6** S2 → **M6.7** S3; every changed card passes the L3 card gate (M9.60, later M9.12) first.

### Map signal (read first)

Board after this pass: **205 open / 27 blocked / 0 in progress / 134 done**
(block headers parsed 2026-11-22 on `af469580` plus this pass; the fenced task
template is not counted). 20 of the open blocks are H. A cycle that moves
none of the four numbers above says so in its first line.

**This pass (23rd):** archive **81 moved** to
`docs/research/todo-history-2026-11-22.md` (each done >24 h by the blame date
of its Status line, named by no live `Depends`/`Unblock`/`Re-opens`, no
`fn 0x…` line); a stale second copy of the preamble and of the 21st-pass
Priorities (328 lines, left by `d0f7ba8`) removed; TODO.md 5910 → 4351 lines
before the new tasks. Added **120 tasks**: M8.H1–M8.H69, M4.64–M4.92,
M3.38–M3.42, M5.73–M5.80, M9.68–M9.70, M2.21–M2.24, M6.22, M6.23, M1.49
(claims C-6980–C-8189). Board repair 2026-11-22 (TL): the KIWI MDP parcel task duplicated `M3.38` with #498's seeded-request task; it is now **M3.42** (C-7780–C-7789) and M3.39 `Depends:` follows; the seeded-request task moved to C-8190–C-8199 because M8.H1 (this pass) already holds C-6980–C-6989. Board defect fixed: M4.63 and M8.C1b both held
C-6870–C-6879 (M8.C1b's rows are in `claims.md`), so M4.63 now has
C-8100–C-8109. `Step:` set on M4.63, M5.67, M9.64. Rule 15: 0 re-opened (not
re-audited this pass). The 22nd-pass text of this section is in git
(`af469580`).

---

## H — Housekeeping

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

- [x] **H45 — `l3_precond`: reachability gate for reopened L3 reader reruns (retro action 4)**
  - Status: done · Owner: task/h45-l3-precond · Critical: no
  - Pair: solo
  - Result: `tools/l3_precond.py` (`--selftest`, `--json`) gates reopened L3 reruns with `READY|BLOCKED|UNKNOWN` + M1.2f/import/input/binding reasons; `cmp_ind_reader` READY (declared inputs, M1.2f sec1 verification mitigated) and `drstr_parser` BLOCKED (M1.2f/compressed-sec1/import/mapping) on real `targets.json` metadata; TODO L3 rerun guidance references it. EXP: `docs/experiments/EXP-2026-11-09-H45-l3-precond.md`. Claims C-3330-C-3333.
  - Depends: M1.12 (reader precheck patterns), M9.20/M9.24 context (entry kinds/mapping)
  - Goal: before any reopened L3 reader run is claimed, make the M1.2f+import+input/binding preconditions explicit and machine-checkable so SE/TL can reject "fourth attempt, same blocker" reruns.
  - Precheck: `python3 tools/reader_precheck.py --selftest` (or existing precheck tooling) passes; reopened L3 reader tasks in TODO list a Precheck/Scope/Stop.
  - Scope: add `tools/l3_precond.py` (or extend `reader_precheck.py`; name in PR) with `--selftest` and `--json` that, for a named L3 target or reader VA/module, reports: executable vs data bytes, compressed-sec1/data dependency (M1.2f), import/input/binding reachability known vs unknown, and a `READY|BLOCKED|UNKNOWN` verdict with reasons. No firmware execution; no vendor bytes committed.
  - Input: `tools/reader_precheck.py`, `tools/cerom.py memmap/comphdr`, `docs/research/reader-coverage.md`, target metadata in `tools/l3_harness/targets.json`, EXPs for M9.6/M9.11/M9.13/M9.17 blockers.
  - Done when: `python3 tools/l3_precond.py --selftest` passes; running it on at least two real target definitions (one runnable/baseline-known, one known-blocked on M1.2f or missing mapping) produces the expected verdicts with reasons in an EXP; TODO L3 rerun guidance references it.
  - Stop: if target metadata lacks stable VA/section fields for a verdict, report `UNKNOWN` with the missing fields (do not guess READY).
  - Claims: C-3330–C-3339


- [x] **M1.2f — Port the nk.exe block codec (`DECOMP_BLK`) to pure Python**
  - Status: done · Owner: task/m1.2f-decomp-blk-python · Critical: no
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` runs the kernel's own `DECOMP_SECT` in PySh4 and `cerom.py decompress --check` reports 245/245 build-A sections OK with `r0 == comphdr uncompressed_len` (EXP-2026-11-19-M1.19-kernel-decomp-wiring); no codec port or QEMU run is needed (M1.19 rule-15 closure).
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Note (PM twelfth pass, H49): **not the L3 gate any more.** Only `INIT`
    bytes need it — 1.67 MB of 30.2 MB compressed (C-3440): sec2 constants,
    the first 98 KB of `Navi.exe` sec1 past the IAT, build-B FILESentry
    payloads (M1.3/M1.4). Import slots and BSS do not (C-3441/C-3442).
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



- [x] **H52 — Audit every cited `fn 0x…` against `.pdata`**
  - Status: done · Owner: task/h52-fn-citation-audit · Critical: yes
  - Depends: M1.25 (done; `--fix-list` gives the 12-row table) — the all-modules table is M1.20, not needed for the cited VAs (SE 2026-11-15)
  - Goal: H51 found three "functions" that are not function starts (`0x0041c7e8` → `fn 0x0041c7dc`, `0x00412bee` → `fn 0x00412ac0`, `0x00542256` → `fn 0x00542250`). A cross-reference search for a mid-function address finds nothing, and an L3 call that enters after the prologue runs with a wrong stack frame. Find every other such VA before more tasks build on them.
  - Precheck: `python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe 0x0041c7e8 0x0041c7dc` prints `INSIDE` then `START`.
  - Scope: every VA written as `fn 0x…`, `sub_…` or "entry" in **every** `docs/format/*.md` the audit scans (not just `firmware.md`: M1.25 finds `INSIDE` in `cmp-ind.md` too), `tools/l3_harness/targets.json`, the constants of `tools/chunk_decoder_l3.py` / `tools/point_walk_l3.py`, open task blocks of `TODO.md`, and the 2026-11-08…11-10 EXPs. Not: re-deriving what the functions do.
  - Input: `grep -rhoE "(fn|sub_|entry) ?0x00[0-9a-f]{6}" docs/format/firmware.md TODO.md tools/l3_harness/targets.json | sort -u`; `nk_decomp.py pdata` accepts many VAs in one call. Classes: `START` (fine), `INSIDE` (wrong entry — give the true start), `GAP` (no record: a leaf function such as the POINT walker `0x003f5194`, or data; confirm a leaf by a direct `jsr`/`bsr` caller with `sh4xref --to`).
  - Hints: start with the L3 targets — `FN_CHUNK` in `chunk_decoder_l3.py` entered at `0x0041c7e8`→`fn 0x0041c7dc`, six bytes in (after five of the six prologue pushes), so the epilogue popped a register that was never pushed; the byte-identical output (M9.11) shows the body is right, but the stack/`r8–r13` state after return is not. The H49 list `0x003f5a1e…0x003f5fc2` and M3.22's `0x00412bee`→`fn 0x00412ac0`, `0x0040e4b2`→`fn 0x0040e28c` look like mid-function labels too. `sh4xref.py` prints `fn 0x…` from a heuristic; compare its labels with pdata on 200 random sites and report the mismatch rate.
  - Done when: an EXP table `VA / where cited / class / true start / fixed in file` covers every cited VA; each `INSIDE` is corrected in `firmware.md` and in the tool constants (re-run the tool's own check after the change), with a claim row per correction; the mismatch rate of `sh4xref`'s `fn` labels is stated.
  - Stop: after the table. A VA whose function does something else than the doc says becomes a new M3 task, not part of this audit.
  - Claims: C-3490–C-3499
  - Result: EXP-2026-11-16-H52-fn-citations; C-3490–C-3499 (remaining stale VAs in `docs/research/fn-audit-2026-11-16.md`). Applied the `fn_audit --fix-list` table: `INSIDE` citations 33 → 0 (9 unique VAs → 0), exit 1 → 0, `--fix-list` empty. `chunk_decoder_l3.py` `FN_CHUNK` 0x0041c7e8 → 0x0041c7dc (DST_SLOT 40 → 16, same byte-identical PASS); `targets.json` `cmp_ind_reader` 0x0041c7dc; `firmware.md`/`cmp-ind.md`/`README.md`/`reader-coverage.md` labels corrected; `point_walk_l3.py` had no entry VA to fix (C-3496). `sh4xref` label audit: 36.5 % mismatch over 200 sites (C-3495). EXPs untouched.

- [ ] **H96 — L3 says "PASS" when nothing new ran (`runnable=1/7`), and no CI job runs `l3check --build-corpus` at all**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: H55 (`--json PATH`, done); H28 owns the *job* and H43 the *generated corpus* — this task is the verdict contract only
  - Goal: the L3 progress signal cannot regress visibly. `python3 tools/l3check.py --build-corpus` on today's corpus prints `counts pass=1 fail=0 skip=0 blocked=6 runnable=1/7` and `RESULT: PASS` with exit **0**, so a later push that adds a blocked reader, or loses the one runnable target, still exits 0; and `grep -n l3check .github/workflows/*.yml` matches only comments, so no PR run of L3 exists (the gate's `fn_audit` SKIPs without the head). QA 14th pass found this while checking the runs, not the files.
  - Precheck: `python3 tools/l3check.py --build-corpus > /tmp/opencode/l3.out 2>&1; echo $?` prints `0` and the output prints `runnable=1/7`; `grep -c 'l3check.py --build-corpus' .github/workflows/ci.yml .github/workflows/l1l2-fixtures.yml` prints `0` for both (H55's `Done when` names the command, not a workflow step).
  - Scope: `tools/l3check.py` only: add a committed baseline (`--baseline PATH`, new file `docs/research/l3-corpus-baseline.json`, no vendor bytes — it lists target names and statuses) so a run whose `runnable` count *drops* or whose a-PASS target becomes FAIL/BLOCKED exits 1; keep exit 3 for "nothing runnable" and keep `RESULT: PASS` honest by printing `runnable 1/7 (baseline 1)` in the summary. `--write-baseline` refreshes it with an EXP naming the change. Do **not** add the workflow step (H28) or a generated-fixture corpus (H43).
  - Input: `tools/l3check.py` (`counts`, `main`, the `RESULT:` block around line 1024), `tools/l3_harness/targets.json` (7 targets, one runnable `cmp_ind_reader` synthetic), H28/H43/H55 blocks.
  - Hints: the baseline is keyed by target **name**, never by line or index (rule: stable key). The synthetic `probe` target and the six `BLOCKED` rows are the negative fixture: drop `cmp_ind_reader` from a temp `targets.json` and the run must exit 1, not 0. Do not pin `blocked` counts as a failure — a reader being unblocked is progress; a runnable target disappearing is the regression.
  - Done when: `python3 tools/l3check.py --build-corpus` prints `runnable 1/7 (baseline 1)` and exits 0; with `cmp_ind_reader` removed from a temp targets file it exits 1 with a `BASELINE LOST` line; `--selftest` covers both; `python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3.json` still parses; `selftest.py --only l3check` passes.
  - Stop: if the corpus is not deterministic enough to baseline by name, baseline only the `runnable` count and record the reason in the EXP; never make a new BLOCKED row fail the gate.
  - Falsifier: today's `main` exits 0 while printing `runnable=1/7` and a second run with one runnable target removed also exits 0.
  - Claims: C-4240–C-4249

- [ ] **H98 — `main` merges on unverified CI: the repo has no branch protection, so a red run blocks nothing**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: — (admin exists on `neutrinus/OSM2Leaf`); H90 is the cost of not having it
  - Goal: a task is "done" when it is on `origin/main` (rule 6), but nothing makes a *green* run a condition of merging. `gh api repos/neutrinus/OSM2Leaf/branches/main/protection` returns **404 "Branch not protected"**, so the 12 red H90 pushes, and the 7 red runs QA found since the last pass, were merged on top of a failing gate; the only defence is a role reading `gh pr checks` (TL prompt), which H90 proved is skipped. The same gap makes "a regression gate" aspirational: H86's local proxy (step rc = gate rc) never fails on an `l1l2_fixtures` regression because that workflow is not the gated step.
  - Precheck: `gh api repos/neutrinus/OSM2Leaf/branches/main/protection 2>&1 | grep -o 'Branch not protected'` prints it; `gh api repos/neutrinus/OSM2Leaf -q .permissions` prints `"admin":true`, so the fix is available to this account.
  - Scope: repo settings only (no workflow file): require the `quality (py3.11)` and `quality (py3.13)` checks on `main` (and `l1l2 (py3.11)`/`(py3.13)` from `l1l2-fixtures.yml`), `enforce_admins: false` so a documented emergency bypass still exists, no required reviews (single-role cycles would deadlock), no dismissal. Record the exact `gh api -X PUT .../protection` command in the EXP so another agent can re-apply it. If the owner refuses (rule: this is the one human decision here), fall back to a committed `.github/workflows/`-independent pre-merge check: a `tools/premerge_check.py` (or extend `gate.py --premerge`) that refuses a non-green `gh run list` for the tip, with the same Done-when measured on a deliberately-red local commit.
  - Input: `gh api .../protection`, `.github/workflows/ci.yml` (job/step names), `l1l2-fixtures.yml`, H90 EXP (the 12 red pushes), H70/H85 history.
  - Hints: the required-context names must be the *job* names CI actually reports (`quality (py3.11)`), not the step name — check with `gh pr checks <a merged PR>` before writing them, or the rule silently never satisfies. Do not require the informational py3.14 leg. Branch protection is reversible and does not touch the repo bytes, so it needs no vendor-data review.
  - Done when: `gh api repos/neutrinus/OSM2Leaf/branches/main/protection` lists the four required contexts (or the fallback tool exists and exits 1 on a red tip, 0 on green); a throwaway red commit on a test branch cannot be merged via the protected path (or the fallback refuses it); the EXP names the applied payload and the date; no workflow logic changed except the fallback tool's selftest.
  - Stop: if the owner declines branch protection, ship only the `--premerge` check, record the refusal in the EXP, and keep this task `done` with `Result:` naming the fallback — do not re-open it each cycle.
  - Falsifier: `main` can still take a commit whose `CI quality gate` run is red and no local check refuses it.
  - Claims: C-4260–C-4269

- [x] **H117 — the push-to-main gate is a shadow run: 16 PRs merged in a 35-minute burst while `main` carried 4 red gate runs, and nothing refused a merge**
  - Status: done · Owner: task/h117-main-shadow-run · Critical: yes · Pair: required
  - Depends: H98 (the pre-merge gate; this is its observed cost), H108 (the QA CI check that should have caught the burst)
  - Precheck: `gh run list --workflow "CI quality gate" --branch main --limit 60 --json conclusion,headSha,createdAt` lists 4 `failure` runs between `2026-11-20T04:12:10Z` and `2026-11-20T04:36:05Z` (`6270c0cc`, `b3333cde`, `a480a8a6`, `98e0e3eb`); `gh pr list --state merged --json number,mergedAt` lists 16 merges between `04:05Z` and `04:45Z`. The failures were real gate defects, not infra: `6270c0cc` `todo_check FAIL exit 1` (`duplicate task ID M4.48 at lines [2231, 2326]`), then `claims_check FAIL exit 1` on the next three (`b3333cde`, `a480a8a6`, `98e0e3eb`). The 16 PRs were merged without waiting for those runs to finish; the first green after the burst is `ac2a199` (#303, the dup-ID fix). The same pattern repeated at 08:45–09:30Z with 3 more `cancelled` runs shadowed by `success` runs.
  - Goal: make each `push`-to-`main` run's verdict a condition of the *next* merge, not a log line a role reads later. Either policy: (a) rework `ci.yml` so a PR run and the post-merge push run are the same verdict the TL reads (required check on the PR, which H98's branch protection then enforces), or (b) a `main`-only watchdog (scheduled or `workflow_run`) that, when the tip run is red, opens a `fix:` issue / red board line naming the SHA and fails; the QA "check the runs, not the files" step reads that instead of a 40-row `gh run list`. Prefer (a) if H98 lands branch protection; (b) is the fallback if the owner declines.
  - Scope: `.github/workflows/ci.yml` (or a new `main-watch.yml`), `docs/research/feedback-loop.md`/QA rows; no gate semantics change (`gate.py`, `claims_check`, `todo_check` untouched). Not: re-litigating H90 (the shallow-clone cause is fixed) nor H98 (branch protection).
  - Input: the 4 red runs above, the 16-PR burst window, `.github/workflows/ci.yml`, H98/H108 blocks, `gh run view <id> --log-failed`.
  - Hints: the burst is a *concurrency* effect — a push run is superseded by the next push (`cancelled`), so "main is green" can be true for a tip whose CI never actually ran the gate on it; a required-check-on-PR model fixes both the shadowing and the merge-on-red. Report the count delta (red runs on `main` per cycle) as the metrics line.
  - Done when: a deliberately-red commit pushed to a scratch branch cannot reach `main` without a failing check blocking it (or the watchdog opens the named issue within one run of the red tip); the EXP counts the red `main` runs in the window before/after and names the policy chosen; `gh run list --workflow <gate> --branch main --limit 20` in the report has no red run that was *shadowed* by merge activity without a board line.
  - Stop: if the owner declines both (a) and (b), record the refusal and the residual risk in the EXP, set `blocked` with `Unblock: <human>`, and do not re-open it each cycle.
  - Falsifier: `git log origin/main` contains a merge whose immediately-preceding `CI quality gate` run for that tip is `failure`, and no issue/board line names it within a day.
  - Claims: C-5750–C-5759
  - Result: EXP-2026-11-20-H117-main-shadow-run; policy (b) shipped (policy (a) parked on H98: `main` unprotected, `gh api …/protection` 404). `.github/workflows/main-watch.yml` + `.github/scripts/main_watch.py` fail on a salient red `main` run and open one `[H117] fix:` issue naming the SHA and the failed job/step; a later green covers a red (shadowed, counted), `cancelled` covers nothing, an empty list is exit 2. Offline selftest `OK (19 checks)`; `--replay` of the 100-run list prints 7 red-tip moments; today's tip `d2fb7b48` is `0 salient`; Done-when control: a deliberately red branch (duplicate claim row) shows `quality (py3.11)`/`(py3.13)` fail on its PR. Claims C-5750–C-5753.

- [x] **H55 — `l3check --json PATH`: the tool writes a report file, not only stdout**
  - Status: done · Owner: task/h55-l3check-json-path · Critical: yes · Pair: solo
  - Depends: —
  - Goal: H42/H43 cannot ingest the L3 result because `tools/l3check.py` defines `--json` as a boolean flag (`action="store_true"`, line ~1082) that merely switches stdout to JSON. `python3 tools/l3check.py --build-corpus --json out.json` exits **2** with `unrecognized arguments: out.json`, so the one command the QA plan (H28, H42, H43) tells CI to run does not exist.
  - Precheck: `python3 tools/l3check.py --build-corpus > /tmp/l3.out 2>&1; echo $?` prints `0`; `python3 tools/l3check.py --build-corpus --json /tmp/l3.json; echo $?` prints `2` and the argparse error above (the defect).
  - Scope: `tools/l3check.py` only: make `--json` take an optional path (`nargs='?'`, `const='-'`) so the flag keeps its current stdout meaning and `--json PATH` writes the same document to `PATH` (atomic write, UTF-8); accept `-` as stdout. Update the help/README example. Do not change the report schema or `--build-corpus` verdicts.
  - Input: `tools/l3check.py` `--json` handling, the report builder around the `counts`/`targets` keys, `tools/progress_report.py --l3-json` (the consumer), H28/H42/H43.
  - Hints: keep backward compatibility — a bare `--json` on stdout is used by scripts today; only the optional-argument form is new. Mirror how `l1l2_fixtures.py --json PATH` already behaves.
  - Done when: `python3 tools/l3check.py --build-corpus --json /tmp/l3.json` exits `0` and the file parses as the same JSON that bare `--json` prints; the selftest covers both forms; `progress_report.py --l3-json /tmp/l3.json` reads it without a schema change; `selftest.py` passes.
  - Stop: if changing the flag breaks a caller, add `--json-out PATH` instead and keep `--json` boolean; record the choice in the task's Result line.
  - Claims: C-3710–C-3719
  - Result: EXP-2026-11-15-H55-l3check-json-path; `--json` is `nargs="?", const="-"`, `PATH` written atomically (UTF-8), `-`/bare = stdout; schema `osm2leaf.l3check/v1` and verdicts unchanged; fixed-corpus file is `cmp`-identical to bare `--json`; `progress_report.py --l3-json` reads it (exit 0). Claims C-3710–C-3713.

- [ ] **H56 — Per-level generated-card progress snapshot (L1/L2/L3 PASS counts + L4/L5 readiness, SKIP never PASS)**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: H41 (L1/L2 matrix), H55 (L3 JSON file), H40 (generated fixture)
  - Goal: the QA target asks for "how far a generated card gets, per level". Today `progress_report.py` aggregates inputs but needs each input handed to it, and no single command answers "where does our generated card stand at L1/L2/L3, and is L4/L5 ready?" without manual assembly.
  - Precheck: `python3 tools/progress_report.py --selftest` passes; `python3 tools/progress_report.py --l1l2-matrix-json <H41 output>` and `--l3-json <H55 output>` accept the shapes (help/EXP-2026-11-09-H47).
  - Scope: a thin driver (extend `progress_report.py --run-tools` or a `tools/progress_snapshot.py`, name in PR) that, from a generated no-vendor fixture: runs the L1/L2 matrix (H41), `l3check --build-corpus --json PATH` (H55), then calls `progress_report.py` with the outputs and prints one Markdown/JSON table `level / runnable PASS / FAIL / SKIP / NOT_COVERED / NOT_RUNNABLE / BLOCKED / verdict`, plus explicit L4-emulator and L5-bench rows that are `NOT RUN (hardware/QEMU unavailable)` unless a status JSON is supplied. SKIP/NOT RUNNABLE/BLOCKED never counted as PASS (rule 13). No vendor data, no QEMU, no network.
  - Input: `tools/progress_report.py` (schema v3), H41 matrix JSON, H55 L3 JSON, `tools/cardcheck.py`/`l2check.py` on the H40 fixture, `docs/research/test-system.md` §status classes, `reader-coverage.md`.
  - Hints: the tool must be able to fail loudly — a fixture that regresses from PASS to FAIL at any level makes the snapshot exit non-zero; a level with no runnable check reports `NOT COVERED`, never `PASS`. L4/L5 rows are readiness flags only (M8/H29), not acceptance.
  - Done when: `python3 tools/<name> --selftest` passes on a synthetic fixture and separates PASS/FAIL/SKIP/NOT_COVERED/NOT_RUNNABLE/BLOCKED; the default PR job can run it with no vendor data; the EXP links one run and maps each column to a level per `test-system.md`; a PASS->FAIL regression in the fixture makes it fail.
  - Stop: if H41 is not landed, build the L3 + readiness rows only and mark L1/L2 `NOT COVERED (H41)` rather than guessing the matrix.
  - Claims: C-3720–C-3729

- [ ] **H57 — Fixture regression baseline: a committed no-vendor baseline and a documented PASS->FAIL gate**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: H41 (matrix), H56 (snapshot)
  - Goal: H41 mentions a "committed no-vendor baseline" and H26's fixtures have PASS/FAIL counts, but no file holds the expected result and no doc states when a baseline may change. Without it "once a level passes, CI fails if it stops passing" (prompt_qa) is unenforceable.
  - Precheck: `git ls-files | grep -i baseline` returns nothing today; `grep -n baseline .github/workflows/*.yml` returns nothing.
  - Scope: a committed baseline file (JSON, no vendor bytes) keyed by `level,file,feature,status` produced by H41/H56 on the named fixture; a `--check-baseline FILE` mode in the reporter that exits non-zero when a baseline PASS becomes FAIL/SKIP/NOT_COVERED (SKIP→FAIL and PASS→anything-not-PASS both fail; FAIL→PASS is an improvement, printed, not an error); workflow README section "regression policy" and a one-paragraph `docs/research/test-system.md` update. Baseline refresh only with an EXP/PR rationale (like `l2check --update-golden`), never to make a failure pass.
  - Input: H41 matrix JSON, H56 snapshot, `.github/workflows/l1l2-fixtures.yml`, `docs/research/test-system.md` §6 (regression gate policy), AGENTS "verification ladder".
  - Hints: store the baseline as sorted keys so a diff is readable; a missing key on a new check is `NEW` (not a regression), a removed key is `DROPPED` (report, do not fail unless it was PASS). Keep the fixture deterministic so the baseline does not churn.
  - Done when: the baseline file exists for the H41/H56 fixture; `--check-baseline` fails on a synthetic PASS->FAIL and passes on the current fixture; the workflow README and `test-system.md` state the policy; `selftest.py` passes.
  - Stop: if H41/H56 choose a different output shape, commit the baseline in that shape and record the mapping in the EXP; do not fork a second schema.
  - Claims: C-3730–C-3739

- [x] **H58 — Make the claims ledger reject non-runnable evidence (`...`/`START`/`MODULE` placeholders, prose loops)**
  - Status: done · Owner: task/h58-claims-runnable-evidence · Critical: yes · Pair: solo
  - Depends: — (`tools/claims_check.py` is on `main`; no other task's block is needed)
  - Goal: the evidence column is the ledger's whole value, but `claims_check.py` only checks IDs and annotations. `C-3612`, `C-3613`, `C-3614` (M1.23) cite a "loop over `cerom.py … modules`" and `--image-start START --module MODULE` that exist only in a `/tmp` heredoc, and `C-3711` (H55) cites `cmp ...`. SE 2026-11-15 reproduced the census (A 149/87,530/20 plain, B 91/21,930/19, C 88/25,243/23) only with a throwaway script — that is exactly rule 16's defect, and it reached `VERIFIED` because no check reads the command. (C-3712 is the subtler "producer command omitted" case; a check cannot see it, so reviewers still read.)
  - Precheck: `python3 tools/claims_check.py` is OK today; `grep -n 'C-3612\|C-3613\|C-3614\|C-3711' docs/research/claims.md | grep -cE '…|\.\.\.|--image-start START|--module MODULE'` prints 3 (C-3612, C-3613, C-3711), and `C-3614`'s evidence is the bare prose "census loop over `pdata.load_table`" with no invocation at all — 4 rows fail a runnable-command rule, so the defect is present, not hypothetical.
  - Scope: `tools/claims_check.py` only: a `bad_evidence()` pass over rows whose Status starts with `VERIFIED`; fail a row when, after the EXP name, its backticked command span (a) contains `...`, `…` or an unexpanded placeholder token (`START`, `MODULE`, `VA`, `<...>`), (b) has no span starting with a known invocation (`python3`, `tools/`, `git`, `curl`, `sha256sum`, `grep`, `cmp`, `stat`), or (c) is a heredoc/`python3 -c` with no `tools/` path. Allow short hash abbreviations matching `[0-9a-f]{4,}…[0-9a-f]*`. Print one line per row and a total; land it as a warning by default and an error under `--strict` so the legacy rows do not block CI.
  - Input: `docs/research/claims.md` (all rows), `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`, `main`), `docs/experiments/TEMPLATE.md`, TODO rule 16, EXP-2026-11-15-M1.23-pdata-wireup, EXP-2026-11-15-H55-l3check-json-path.
  - Hints: do not flag English prose `…` ("switch 7…15") — require the span to open with a known invocation, so `C-207` and the hash rows stay clean. Reuse H53's `--strict` (one flag, two rules) rather than a second parser; H53 owns the board checks, this owns the ledger. Keep the duplicate/unregistered/annotation checks untouched.
  - Done when: `python3 tools/claims_check.py --selftest` passes (synthetic `cmp ...` row fails, a hash-abbreviation row passes, a prose row without a command fails, an EXP+real-command row passes); default `claims_check.py` still exits 0 on the current ledger and prints the non-runnable row count; `--strict` exits 1 and names at least `C-3612`, `C-3613`, `C-3614`, `C-3711`; `selftest.py` passes.
  - Stop: if the allowlist grows past ~20 IDs, ship the report and the count with `--strict` opt-in (default still 0) and hand enforcement to H53, recording the row count in the EXP.
  - Claims: C-3770–C-3779
  - Result: EXP-2026-11-19-H58-claims-runnable-evidence — `bad_evidence()` names 347 of 1,376 VERIFIED rows at `934d76e` (ellipsis 31, placeholder 19, inline 3, no-invocation 294), including C-3612/C-3613/C-3614/C-3711, not C-207/C-3510; Stop applied (347 ≫ 20): default and `--strict` (the gate) stay exit 0 and print the count, `--strict-evidence` exits 1; `--selftest` 47 checks. Enforcement in `--strict` handed to H53/H66 (C-3770–C-3775).

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

- [ ] **H59 — Trace the test-system plan to the board so "plan complete?" is checkable**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: H55 (done); coordinates H28/H40–H44/H56/H57/H58, M9.31/M9.12, M8*, H29
  - Goal: one pass must answer "is the QA test-system plan complete, and which gaps remain" from data, not by re-walking prose. Every `prompt_qa.txt`/`test-system.md` requirement maps to a task, a landed artifact, or an explicit decision; orphans (a `done` task the plan still names as future work) and untracked requirements become visible each QA run.
  - Precheck: `git ls-files | grep -i traceab` empty; `grep -c "## 7." docs/research/test-system.md` = 0; `grep -n "^### Requirement" TODO.md` empty.
  - Scope: docs + one small tool, no vendor data. (1) Add §7 "Requirement traceability" to `docs/research/test-system.md`: rows `require, level, tasks, evidence, state`, one per requirement (per-level generated-card progress, per-file/per-feature L1/L2, L3 ran-on-our-data, L4 readiness, L5 readiness, SKIP/NOT_*/BLOCKED never PASS, no vendor in PR CI, IMG256 manual/weekly, regression gate, fixtures). (2) `tools/test_plan_check.py` (`--selftest`, `--json`, `--strict`) parses §7 + TODO status lines and fails on: a row whose tasks are all `done` but whose evidence file/tool is absent (orphan/`done` without artifact); a task ID not in TODO; a row with no task and no `decision:` reason; a `landed` row whose evidence command is not in the repo. Prints `plan: complete` only when every row is `landed` or `decision:`. (3) QA runs it before adding tasks; a new requirement without a row fails.
  - Input: `prompt_qa.txt`, `docs/research/test-system.md` §2–§6, `.github/workflows/{ci,l1l2-fixtures}.yml` + README, TODO H28/H40–H44/H56/H57/H58/M9.31/M9.12/M8*/H29, `tools/todo_check.py` block/`Status:` regex.
  - Hints: reuse `todo_check.py`'s block regex, do not write a second TODO parser. The oracle is a committed tool/workflow/EXP, not a `Result:` sentence. 100 % is not required: a requirement may be `decision: manual L5, not automated` and still be complete.
  - Done when: `python3 tools/test_plan_check.py --selftest` passes on synthetic positive/negative tables (missing task, orphan, unlanded evidence fail; a `decision:` row passes); `python3 tools/test_plan_check.py` exits `0` and prints `plan: complete` or names the gaps on the current §7; deleting one evidence task's `Result:` in a temp copy makes it exit `1`; `selftest.py` passes.
  - Stop: if the table needs >~20 rows to stay honest, keep the per-level rows and record the rest in §7 prose with `NOT TRACKED: <reason>`; do not build a second issue tracker.
  - Claims: C-3780–C-3789

- [x] **H66 — H64's `--json` parity rule: a follow-up to the parsed-then-unused flag class**
  - Status: done · Owner: task/h66-json-parity-flag · Critical: no · Pair: required
  - Depends: — (`tools/claims_check.py` is on `main`); coordinates H58 (the *command* form of evidence) and H61 (the *name*)
  - Goal: H64's navigator caught `--json` parsed then unused — the third such flag this week (SM retro-5 `Watch`). `claims_check` proves a command exists (H58) and the EXP file exists (H61), but nothing proves an evidence command actually *wrote* the file it names, and nothing scans for a flag the tool accepts but never reads. The four claims this pass (`C-3493`, `C-3494`, `C-3840`, `C-3843`) already show the weak spots: `…` in the command span and "same command as C-3840" (prose reference, no invocation). Make "the evidence command writes the named path" a check, not a reviewer's memory.
  - Precheck: `grep -nE "'…'|same command as" docs/research/claims.md | grep -E 'C-349|C-384'` prints the four rows above; a flag-audit script today (`for f in tools/*.py`: collect `add_argument("--x")`, count `args.x`) lists ≥10 flags with zero `args.<dest>` uses (e.g. `sh4dis --check-real`, `l3check --build-corpus`, `one_tile_pipeline --factory-tile`) — the same class H64's `--json` was, not all bugs but all unproven.
  - Scope: `tools/claims_check.py` + a small `--flag-audit` mode only, no vendor data. (1) In `bad_evidence()` (H58's parser) treat a `…`/`...` inside the command span and a bare prose reference (`same command as C-xxx`) as non-runnable, not just the `START`/`MODULE` placeholders. (2) `--flag-audit` sweeps `tools/*.py` for `add_argument` whose `dest` is never read and lists them as warnings; a flag on a `VERIFIED (tool)` claim's own command is an error under H58's `--strict`. Not: editing any claim (that is the task that owns the EXP), auto-fixing flags, or executing the evidence commands.
  - Input: `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`, `bad_evidence` from H58), `docs/research/claims.md` rows `C-3493`, `C-3494`, `C-3840`, `C-3843`, `tools/one_tile_pipeline.py` `--json` (the H64 fix to model the parity after), `tools/selftest.py`.
  - Hints: a flag can be legitimately parsed-then-forwarded (`args` passed to a helper), so resolve the dest through a one-hop `getattr`/kwargs pass before calling it unused; keep `--flag-audit` warning-only for the legacy flags (`--selftest`, `--check-real`) and make only a *claim-evidence* flag an error. The positive control is `one_tile_pipeline --json` (parsed, writes, selftest re-parses); the negative is `--check-real` (`sh4dis`), which is real but not evidence.
  - Done when: `python3 tools/claims_check.py --selftest` covers a `…`-in-command row, a `same command as C-x` row, and a clean `--json PATH` row (first two fail under `--strict`, third passes); `python3 tools/claims_check.py --flag-audit` lists the unused flags and names the four window claim IDs; `--strict` exits 1 on the current ledger naming `C-3493`, `C-3494`, `C-3840`, `C-3843`; default stays exit 0; `selftest.py --only claims_check` passes.
  - Stop: if the flag sweep has too many false positives (forwarded args), ship only the `bad_evidence()` prose/`…` rule (the H58 extension) and record the flag sweep as `NOT SHIPPED: <reason>` for a later task; do not suppress a real claim-evidence flag.
  - Claims: C-3870–C-3879
  - Result: EXP-2026-11-22-H66-json-parity (C-3870–C-3876): claims_check gains a same-command evidence reason, a four-row --window-strict error (C-3493/3494/3840/3843; default and bare --strict stay 0 so the gate is not turned red for 60 unrelated ellipsis rows), and an ast-based --flag-audit (4 real parsed-but-unread flags, named; warning-only). selftest 59 checks; tool/claims_check selftest PASS; strict+count rc=0. libd: fn_audit/selftest red on the base is pre-existing (M1.40 overlay + M3.37 ghost ref), not H66.

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

- [x] **H78 — `claims_check --strict` must run the count rule, and a docs-only EXP edit must not re-pin a claim's measured revision**
  - Status: done · Owner: task/h78-count-gate · Critical: no · Pair: required
  - Depends: H74 (the count rule and `--strict`), H75 (the row that reproduced it), H76 (the l3 suite this must not disturb)
  - Goal: on `main` at `95abb5d` `python3 tools/claims_check.py --strict` exits 0 while `--strict --count-check` exits 1 with `COUNT C-3704 claims 26, tools/fn_match.py prints 29 (ec58d12…)`. Two defects: (a) `--strict` never runs `count_problems`, so the only red part of the ledger is invisible to the standing gate; (b) `_pinned_revision` falls back to `_exp_revision` — the EXP file's **last** commit — so H75's required `Correction (H75)` section moved the measurement from `334f092` (26 checks, the number the claim states) to `ec58d12` (29, main's later tool). Bisected: `--count-check` is 0 mismatches at `4dce4dd`/`e0a8bf5` (EXP head `334f092`) and 1 from `95f7964` (#199) on (EXP head `ec58d12`). Appending a correction to an EXP must not change what its claims are measured against.
  - Precheck: `python3 tools/claims_check.py --strict >/dev/null 2>&1; echo $?` prints `0`; `python3 tools/claims_check.py --strict --count-check 2>&1 | grep -c '^  COUNT'` prints `1` (C-3704); `git log -1 --format=%h -- docs/experiments/EXP-2026-11-16-M1.27-fn-match-leaf.md` prints `ec58d12`.
  - Scope: `tools/claims_check.py` only, plus the claim/EXP text the new rule needs. (1) Make `--strict` run the count rule (or record, in the docstring and the `--help` text, that `--strict` deliberately does not and name the gate that does) — if the former, `--strict` must exit 0 on a ledger whose claims are all honest. (2) Replace the "EXP last commit" fallback with a **date-measured** revision: an EXP's `**Date:**` line is the record's own time, so resolve the tool revision at that date (`git rev-list -1 --before=<date>T23:59 <path>`) or require the claim/EXP to name a commit; a later docs-only edit must not move it. Keep the explicit-commit path (C-3704 names `2709645`) working. (3) Add `--selftest` cases: a claim measured at an EXP whose file is edited *after* its date still reports the date's tool count (not the later one), and a genuinely wrong count still fails. Not: editing C-3704's number (26 is the merge-time count), nor a `Pair:` or numbering change.
  - Input: `tools/claims_check.py` (`count_problems`, `_run_selftest`, `_exp_revision`, `_pinned_revision`, `check()`, `main()`), `tools/selftest.py::test_claims_check` (runs `check()` with `run_counts=False` — the reason no standing gate sees this), EXP-2026-11-16-H74-claims-count-check, EXP-2026-11-16-H75-m1.27-evidence, `docs/research/claims.md` C-3704/C-3951–C-3957.
  - Hints: do not mask the defect by making `--count-check` warn-only; the point is that H74/H75's oracle must be red when it is wrong. If the date rule is too coarse (two tools changed the same day), prefer the explicit-commit form and mark a row that names neither `HYPOTHESIS (no measurement revision)` rather than silently using the file's head. `git log --since` on the EXP is what H75's correction defeated.
  - Done when: `python3 tools/claims_check.py --count-check` exits 0 on `main` with C-3704 at its named `2709645` count; `--strict --count-check` exits 0 on the clean ledger and exits 1 on a fixture whose pinned count differs (exercised by `--selftest`); editing an EXP file (a `Correction` section) after its date does not change the reported measurement revision (a selftest case); `python3 tools/selftest.py` stays green.
  - Stop: if no date/commit rule can distinguish H75's append from a real tool change without hand-maintaining a table, ship the `--strict` half and record the revision rule as `NOT SHIPPED: <reason>` with the bisect count, and hand the per-row revision to H75's owner.
  - Result: EXP-2026-11-16-H78-claims-strict-count; C-4010–C-4016. `--strict` now runs the count rule (`_run_counts`), so the real-ledger `--strict` and `--count-check` both exit 0 with `count mismatches: 0`; the measurement revision is the newest commit that changed the EXP *and* a `tools/*.py` file, so H75's docs-only `Correction` append no longer re-pins C-3704 (measured `334f092` -> 26, not `ec58d12` -> 29). A one-digit change still fails (C-3704 26->25 exit 1); a claim whose EXP record exists but has no measurement revision is skipped, not measured on the working tree; `--selftest` 25 checks (all four numbers from the commands above); `selftest.py` 90/0/23 with the head.
  - Claims: C-4010–C-4019

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

- [x] **H82 — Stamp the zlib interpreter into recompression evidence (this host's default `python3` is zlib-ng)**
  - Status: done · Owner: task/h82-zlib-stamp · Critical: no · Pair: solo
  - Depends: — (`tools/zlibinfo.py` exists); coordinates H58/H66 (evidence form) and every `*.cmp`/`LEV3456R` writer claim
  - Goal: on this host `python3 --version` prints `Python 3.15.0` and `python3 tools/zlibinfo.py` prints `zlib: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)`, yet several EXPs in the window write `python3 3.13.1` (H76/H75/H71) or `python3 3.15.0` (M1.31/M1.26/H74) without saying which interpreter has stock zlib 1.3.1. AGENTS.md makes a byte-identical recompression claim unverifiable on zlib-ng, so the field must name the interpreter that produced the bytes, not the one that printed a log line: `python3.13` here is 1.3.2 and `python3` is zlib-ng, so neither default is the 1.3.1 the writer claims assume.
  - Precheck: `python3 tools/zlibinfo.py` exits 0 and names `zlib-ng`; `python3 tools/zlibinfo.py --require-stock-zlib` exits 3 with `needs stock zlib` (so the tool already knows, the EXPs do not use it).
  - Scope: `docs/experiments/TEMPLATE.md` (one line in the Tools row), `prompt_common.txt` (one bullet), and `tools/zlibinfo.py` (a `--stamp` mode that prints nothing on a standard stock runtime and a `WARNING` line otherwise, so a log is self-describing). No tool's compression behaviour changes; no claim is rewritten.
  - Input: `tools/zlibinfo.py` (`classify`, `Runtime.reference`, `--require-stock-zlib`), `docs/experiments/TEMPLATE.md` Tools row, `prompt_common.txt`, EXP-2026-11-05-06-cmp-writer (the `python3.13` precedent), AGENTS.md "Writing data back".
  - Hints: the pin is stock zlib **1.3.1**, and the two interpreters on this host are 1.3.2 and zlib-ng — so the correct field is the `zlibinfo.py` line or `zlib 1.3.1` only when the run really used it. Do not change `--require-stock-zlib`'s exit codes; EXPs that legitimately record `UNVERIFIABLE` keep their exit 3.
  - Done when: `python3 tools/zlibinfo.py --stamp` prints nothing on a stock 1.3.1 runtime and one `WARNING` line on any other (a `--selftest` case, both injected); TEMPLATE's Tools row and `prompt_common.txt` require the `zlibinfo.py` line for any recompression claim; `python3 tools/selftest.py` stays green.
  - Stop: if a per-EXP edit of the window's six files would touch claims, ship the template/prompt/stamp half and record the EXP backfill as a one-line follow-up (never retype a tool version).
  - Claims: C-4050–C-4059
  - Result: EXP-2026-11-22-H82-zlib-stamp; zlibinfo --stamp warns on non-1.3.1, silent on stock 1.3.1; selftest 182/0/21 green

- [x] **H83 — A board-ref lint: every `TASK#ref` resolves, and a task's normative text never re-states its priority**
  - Status: done · Owner: task/h83-board-ref-lint · Critical: no · Pair: required
  - Depends: H77 (fence-aware scanners, same tool family); coordinates H53 (`todo_check --strict`)
  - Goal: the board's priority prose has rotted repeatedly in ways no gate sees: the header said "next batch: M1.31 → M1.26 → M1.22b" after all three merged, "Take first" listed H74/H75/H71 as ready after they merged, Q1 listed M9.12 "only after M9.31" while M9.12 is blocked *on* M9.31, and H53's block described a `--strict` that had existed for 11 cycles. Each of those cost a cycle of re-derivation, and the mechanics exist already (`todo_check` parses every block). Make the two mechanical classes fail loudly, so a stale sentence is a red gate, not prose archaeology.
  - Precheck: `grep -c 'next batch' TODO.md` and `grep -c 'Take first' TODO.md` show the prose is hand-maintained; `python3 tools/todo_check.py` exits 0 today, so no gate sees it. Print the current count of task-ID mentions in the Priorities section (`python3 - <<'EOF'` probe in the Scope) as the baseline.
  - Scope: `tools/todo_check.py` only (a `--board-refs` mode, on by default as warnings, errors under `--strict`): (1) every `**ID**`/`**ID` mention in the Priorities section resolves to a block that still exists; (2) a `Take first`/`next batch` line that names a task is flagged when that task's `Status` is not `open`/`blocked`; (3) a *done* task named as the current blocker of an open one (`Depends:`/`Unblock:`) is a drift report, not an error (the PO may deliberately keep the history). No prose rewrite; the PO edits on the report.
  - Input: `tools/todo_check.py` (`check()`, block parser, `--strict`), TODO.md Priorities/take-first sections, the retired H53/H74/H75/M9.12/M9.31 sentences as the negative fixtures.
  - Hints: rule 15 drifts are already a `todo_check --strict` error class in H53; reuse its parser, do not add a second markdown reader. Treat `H81`-style blocks ("close the seven…") as naming a set, not a blocker, or the lint will cry wolf on the cleanup task itself. A `done` task inside a historical sentence ("Cycle 8 merged **M1.31**") is legitimate — only a *ready*/blocker claim is wrong.
  - Done when: a fixture Priorities line naming a done task as "next" fails under `--strict` and warns without it; a sentence naming a done task as history passes; `python3 tools/todo_check.py` exits 0 on today's board and prints the board-ref warning count; `python3 tools/selftest.py` stays green; the EXP records the before/after stale-ref count on the real board.
  - Stop: if distinguishing "history" from "next/before" needs natural-language judgement beyond a fixed verb list (`next`, `then`, `Take first`, `ready`, `blocked on`, `only after`), ship the `#ref`-resolves half (pure mechanics) and record the prose half as `NOT SHIPPED: <reason>`.
  - Claims: C-4060–C-4069
  - Result: EXP-2026-11-22-H83-board-ref-lint; C-4060–C-4066. tools/todo_check.py --board-refs lints the first Priorities section: unresolved bold IDs, done IDs under next/then/Take first/in flight, and done IDs as a current blocker (drift, warning-only). Warnings by default, ERRORs under --strict; findings are structural and never baselined (H128). At bd92ec6a on origin/main 17b22eaf: unresolved 0 / not-next 4 (H105, M9.58/M9.60/M9.61) / drift 0 / sections 1, exit 0; --strict adds 4 board-ref ERRORs (22 total); gate 5 pass; selftest 184/0/21; todo_check selftest 80 checks. Prose half shipped; the four stale sentences are the PO's (EXP Follow-ups).

- [ ] **H84 — The QA-prompt manual/weekly IMG256 regression has no workflow: add the `workflow_dispatch` + scheduled job**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H25 (the CI skeleton), H28 (the same "optional IMG256 mode" contract, which stays about `l3check`); QA 2026-11-16 12th pass found the gap
  - Goal: `prompt_qa.txt` requires that "IMG256 / vendor-firmware-head regressions run **manually or weekly by QA** (`workflow_dispatch`/scheduled, approved runner/cache, SHA-256 verified), not as default PR CI", and `tools/realcheck.py` already implements the honest exit codes (`0 PASS/FAIL run`, `2` no image, `--require-image` turns a missing slice into `FAIL` exit 1). But **no workflow file has `workflow_dispatch` or `schedule`**: `grep -lE 'workflow_dispatch|schedule' .github/workflows/*.yml | wc -l` prints `0`, so the only real-bytes regression (`realcheck.py IMG256`) never runs anywhere. On this host `python3 tools/realcheck.py IMG256` prints `realcheck: 0 PASS, 0 FAIL, 8 SKIP` and exits **2** — the image is absent, which is exactly the case the policy covers with an explicit skip, not a silent gap.
  - Precheck: `grep -lE 'workflow_dispatch|schedule' .github/workflows/*.yml | wc -l` prints `0`; `python3 tools/realcheck.py IMG256; echo $?` prints `2` and `0 PASS, 0 FAIL, 8 SKIP`; `python3 tools/realcheck.py IMG256 --require-image; echo $?` prints `1` with eight `FAIL … no image: …`.
  - Scope: one new `.github/workflows/firmware-regression.yml` (name in PR) with `on: {workflow_dispatch, schedule}` only — **never** `pull_request`/`push` — that (1) resolves the 256 MiB head from a cache or a documented rule-11 fetch (`tools/fetch_image.py --image IMG256`), (2) verifies the pinned SHA-256 (`92aa525d…007f9`; `tools/verify.py`/`fetch_image.py --verify`), (3) runs `python3 tools/realcheck.py IMG256 --require-image` and optionally `tools/l3check.py --build-corpus --json`, (4) uploads the JSON/text as an artifact and a job summary, and (5) states `SKIP (no image on this runner)` explicitly — never a pass — when the cache misses. Update `.github/workflows/README.md` with the policy and the cost. No vendor bytes in the repo, no PR trigger, no `l3check --card` gate here (that is M9.12/H43).
  - Input: `.github/workflows/ci.yml`, `.github/workflows/l1l2-fixtures.yml`, `.github/workflows/README.md`, `tools/realcheck.py` (`--require-image`, exit codes), `tools/fetch_image.py` (`IMG256`, `--part 256M`), `tools/verify.py`, H28's Stop (a download that is unstable on the runner becomes `workflow_dispatch` only — this task makes that the *only* mode).
  - Hints: reuse `realcheck.py`'s exit codes verbatim — exit 2 is a **skip**, not a red job; a scheduled job that turns "no cache" into red trains people to ignore it. If the runner has no network access to `files.viaaq.eu`, make the job a no-op with an explicit `SKIP` summary and a link to the local run, and record that in the workflow header. Keep the job ≤ 20 min like the others.
  - Done when: `workflow_dispatch` on a machine with the cached head runs `realcheck.py IMG256 --require-image` and the job summary says `PASS`/`FAIL` per check with the artifact; with no head it says `SKIP (no image)` and the job is neither green-as-passed nor red; the workflow never triggers on `pull_request`/`push`; `.github/workflows/README.md` documents it; `python3 tools/selftest.py` unchanged.
  - Stop: if the approved runner cannot cache or fetch the head within the job timeout (7.4 GB images are out of scope; only the 256 MiB head), ship the `workflow_dispatch` skeleton with an explicit `SKIP: no image` path and record the fetch gap in the EXP; do not vendor the head.
  - Claims: C-4070–C-4079

- [x] **H87 — `fn_audit.US_BUILD_STARTS` still calls itself the M1.22b placeholder, but M1.22b merged**
  - Status: done · Owner: task/h87-us-build-comment · Critical: no · Pair: solo
  - Depends: M1.22b (merged: it added the six pool-only US VAs and the per-build map)
  - Goal: the comment above `US_BUILD_STARTS` (`tools/fn_audit.py`, the block starting "The list is the M1.28 fixture's US side … a per-build map (M1.22b) will replace it") is now false: M1.22b **merged** (PR #203), added its six VAs, and the map it promised is the `build` field in `tools/l3_harness/targets.json` plus the EU→US table in `docs/format/firmware.md`. A reader who greps for "M1.22b" sees a task they think is open.
  - Precheck: `grep -n "will replace it" tools/fn_audit.py` prints one line; `grep -c "0x0044219C\|0x004410B4\|0x0043A378\|0x00433458\|0x003EC274\|0x0041EB1C" tools/fn_audit.py` prints `6` (the M1.22b additions are present); `git log -1 --format=%s --grep="M1.22b" origin/main` names the merge.
  - Scope: the comment above `US_BUILD_STARTS` only, plus the six inline comments if they name a still-open task. No values, no code, no other file.
  - Input: `tools/fn_audit.py` lines 152–166; `docs/format/firmware.md` "EU→US function matches"; EXP-2026-11-16-M1.22b-eu-us-census.
  - Hints: say what the list is now (`the EU→US map's US side, which M1.22b extended; a per-module build map is still a follow-up`) and point at the two files that carry the map. Do not delete the list — `fn_audit` uses it to skip US VAs.
  - Done when: the comment names no task as open-to-replace and points at `docs/format/firmware.md` and `tools/l3_harness/targets.json`; `python3 tools/fn_audit.py --selftest` passes; `python3 tools/todo_check.py` passes.
  - Stop: none.
  - Result: EXP-2026-11-17-H87-us-build-comment; C-4100–C-4101. The comment above `US_BUILD_STARTS` now names the list as it is (the M1.28 fixture's US side + M1.22b's six pool-only twins) and points at `docs/format/firmware.md` and `tools/l3_harness/targets.json`; `will replace it` count `0`. Both counts are pinned to H87's own revision `381879b`: `US_BUILD_STARTS` `12` entries (`git show 381879b:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'`) and `fn_audit --selftest` `OK (70 checks, 0 failed)` there. `main` `9beb6a4` ships `15` entries and `OK (72 checks, 0 failed)` (`398db35`): `e199373` added the three POINT-walker starts and `f1c8dbb` the two H88 selftest cases — EXP-2026-11-18-H91.
  - Claims: C-4100–C-4109

- [x] **H91 — M1.22's shipped `US_BUILD_STARTS` is 15 entries, but H87's Result and C-4101 say it "stays 12"**
  - Status: done · Owner: task/h91-us-build-starts-count · Critical: no · Pair: required
  - Depends: — (M1.22 `e199373` and H87 `381879b` are both on `main`)
  - Goal: H87's `Result` and C-4101 assert `US_BUILD_STARTS` "stays `12`"; the list `main` ships has **15** entries because M1.22 added the three POINT-walker VAs (`0x0041DB44`, `0x0041C370`, `0x0041E63C`) `git rev-list --count 381879b..e199373` commits later (`6`,
  `4` non-merge). The number was true on H87's branch and false at its merge — the exact "number quoted from a command, then moved by another merge" class prompt_common's quote rule exists for. H87's other count, `OK (70 checks, 0 failed)` in C-4101, is stale the same way (`72` from `f1c8dbb`, H88's two `--corpus` cases — not M1.22; EXP-2026-11-18-H91).
  - Precheck: at `398db35` `git show 398db35:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'` prints `15` and at `381879b` the same command prints `12`; `python3 tools/fn_audit.py --selftest | tail -1` prints `OK (72 checks, 0 failed)` (from `f1c8dbb`; `70` at `381879b`).
  - Scope: docs only — TODO.md H87 `Result`, the whole H87 EXP (`docs/experiments/EXP-2026-11-17-H87-us-build-comment.md`: Inputs, Observations, Reproduction, Method, Interpretation, Conclusion), and the C-4101/C-4112 wording. The task explicitly authorises this edit to an append-only record (the counts it quotes are the defect being fixed); the record keeps its own revision pins. No tool or test change.
  - Input: `git log --oneline -- tools/fn_audit.py` (`2e0bed9`, `381879b`, `e199373`), the H87 EXP, `docs/research/claims.md` C-4101/C-4112.
  - Hints: do not replace `12` with a new bare `15` either — say "12 at `381879b`, 15 at merge because `e199373` added three POINT-walker starts" and pin every count to a revision the same way. C-4101's "70 checks" and H88's "72" are the same defect one task over; fix both in this pass.
  - Done when: no line in H87's block, its EXP or C-4101 says the merged list is `12`, and every quoted count names a revision and a command; `python3 tools/claims_check.py --strict --count-check` OK; `python3 tools/todo_check.py` OK.
  - Stop: if the reviewer prefers a tool-side guard instead, stop and hand that half to H92 rather than inventing a second check here.
  - Falsifier: after the edit, `{ sed -n '/\*\*H87 —/,/Claims: C-4100/p' TODO.md; cat docs/experiments/EXP-2026-11-17-H87-us-build-comment.md; grep '^| C-4101' docs/research/claims.md; } | grep -c 'stays \`12\`'` prints non-zero, or a quoted count in those surfaces has no revision. (A literal whole-file count stays >=2 by design — H91's Goal and H92's Precheck quote the defect — so it is not the check.)
  - Result: docs/experiments/EXP-2026-11-18-H91-us-build-starts.md; C-4140–C-4141. H87's `Result`, its EXP and C-4101/C-4112 now pin every count to a revision and a command: `US_BUILD_STARTS` `12` at `381879b` and `15` at `398db35`/`main` `9beb6a4`, `fn_audit --selftest` `OK (70 checks, 0 failed)` at `381879b` and `OK (72 checks, 0 failed)` from `f1c8dbb` (H88's two cases, `git rev-list --count 381879b..f1c8dbb` = `3`, `2` non-merge). Scoped Falsifier grep `0`, `claims_check --strict --count-check` OK, `todo_check` OK. The prose-count guard stays H92.
  - Claims: C-4140–C-4149

- [ ] **H92 — No gate covers the other direction of the count rule: a claim quoting a count the tree no longer prints**
  - Status: blocked · Owner: task/h92-count-guard · Critical: no · Pair: required
  - Blocker: `--prose-counts` is off by default (`grep -c 'prose-counts' tools/gate.py` prints `0`), so no standing gate fails on the H87 `stays` class and H92's `Done when` ("`python3 tools/gate.py` green on `main`" with the rule standing) and its Falsifier are only testable once the rule is wired; the code, selftest and EXP are complete.
  - Unblock: H111 (wires `--prose-counts` into `tools/gate.py`)
  - Depends: H78 (`--count-check` is on `main`), H91 (the defect it should have caught)
  - Goal: `claims_check --count-check` fails when a claim's *selftest-count* pin no longer matches the tool. It stays green when a count quoted in a claim, an EXP `Observations` block or a task `Result` is stale without being a selftest count — which is how H87's `12` (shipped as 15) and H90's shallow-clone `count mismatches: 9` both survived. The safe shapes are few and mechanical: `grep -c` counts, a named list length (`US_BUILD_STARTS`), and `OK (N checks, 0 failed)`.
  - Precheck (re-pointed 2026-11-18 after H91 merged; the old form quoted H87's `stays `12`` line, which H91 fixed): `python3 tools/claims_check.py --strict --count-check` prints `count mismatches: 0` and `claims_check: OK` while `grep '^| C-3894 ' docs/research/claims.md | grep -c 'returns 176 tasks'` prints `1` and the tree prints `229` at `HEAD` `5630048` (`228` at `102fb69`, the 229th block being H111's own) via `python3 -c "import sys; sys.path.insert(0,'tools'); import todo_check; print(len(todo_check.parse_tasks(open('TODO.md').read())))"` — a stale prose pin the gate cannot see. The shape is not a one-off: `grep '^| C-3740 ' docs/research/claims.md | grep -c 'prints `13 5`'` prints `1` and `python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"` prints `13 5`, i.e. a correct `prints N` pin a re-run can confirm; and at the merge before H91, `git show c6e5df3^:docs/research/claims.md | grep '^| C-4101' | grep -c 'stays `12`'` prints `1` while `git show c6e5df3^:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'` prints `15` — the historical witness that the old Precheck used.
  - Scope: `tools/claims_check.py` only: a `--prose-counts` mode (off by default) that reads `<command> prints N`, `stays N` and `OK (N checks` out of a claim's Evidence cell, re-runs only an allowlisted command shape (`grep -c` or `python3 -c`, never an `archive/…` input), and reports `STALE COUNT C-xxxx: claims N, command prints M`. No new tool; no claim-text edits; not enabled in `tools/gate.py` in this pass.
  - Input: `tools/claims_check.py` (`_run_counts`, `_exp_revision`, `_run_selftest`, `main`), H78's count rule and selftest cases, H87's Result as the negative fixture, H90's shallow-clone skip as the shape to reuse.
  - Hints: reuse H78's revision rule — a prose count with no measurement revision is skipped, never failed; do not parse arbitrary prose for numbers (that is how a gate cries wolf). A bare `stays 12` next to a `grep -c` is the case to catch; `12 at <sha>` must stay clean. A `stays 12` with no command and no `--selftest` in the cell is not measurable: list it, do not guess.
  - Done when: a synthetic row `… stays 12` whose `grep -c` prints 15 is `STALE COUNT` with exit 1; `<N> at <sha>` and a revision-less row are clean; `--selftest` covers all three; `python3 tools/gate.py` green on `main`.
  - Stop: if fewer than three real prose-count shapes are safe to re-run, ship the allowlist plus one mutation case, list the rejected shapes in the EXP, and leave enforcement off by default.
  - Falsifier: a `grep -c`-backed `stays 12` whose command prints 15 is not `STALE COUNT` with exit 1, or a correct `15 at <sha>` row goes red.
  - Claims: C-4150–C-4159

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

- [x] **H90 — CI is red on `main`: a shallow `actions/checkout` makes `claims_check --count-check` measure old pins against today's tools**
  - Status: done · Owner: task/h90-ci-shallow-count · Critical: yes · Pair: required
  - Depends: — (H85's CI gate step and H78's `_exp_revision` are on main)
  - Goal: `main` was red on `CI quality gate` for 12 consecutive pushes, from `1889340` (H85's merge, #206) to `2b3d1b4`, the last green being `3f9c0b2` (#205) — while the same command is green locally. Cause: `actions/checkout@v4` defaults to `fetch-depth: 1`, so `_exp_revision` (`git log --format=%H -- <EXP>`) returns only the tip, every claim is "pinned" to the tip, and 9 old selftest counts (C-568 46/411, C-570 186/390, C-650 391/390, C-3704 26/33, C-2085 44/62, C-960 15/19, C-1060 48/68, C-1994 18/19, C-3934 58/72) are measured against today's tools. In a depth-1 clone of `3d79bcc` the tool prints `count mismatches: 9`; after `git fetch --unshallow` it prints `0`.
  - Precheck: `git clone --depth 1 file://$PWD /tmp/x && (cd /tmp/x && python3 tools/claims_check.py --strict --count-check | tail -3)` → `count mismatches: 9` / `claims_check: FAILED`; add `git fetch --unshallow` → `count mismatches: 0` / `claims_check: OK`.
  - Scope: `.github/workflows/ci.yml` (checkout `fetch-depth: 0`, with a comment saying why) and `tools/claims_check.py` only: a shallow history cannot identify an EXP's measurement revision, so `_exp_revision` returns `None` there (the H78 rule already skips a record with no measurement revision — this is the same skip, not a new leniency) and the tool prints `count check: skipped (shallow clone …)`. No claim/EXP text changes, no gate semantics change on a full checkout.
  - Input: `.github/workflows/ci.yml`, `tools/claims_check.py` (`_exp_revision`, `_run_counts`, `main`), the H78 selftest cases.
  - Hints: the repository pack is 3.2 MiB / 809 commits, so a full fetch is cheap and restores the *real* rule in CI; do not instead add the count mismatches to an allow-list.
  - Done when: (a) `python3 tools/claims_check.py --selftest` passes and includes a shallow-history case; (b) a depth-1 clone prints `count check: skipped (shallow clone` and `claims_check: OK` with exit 0; (c) the same clone after `--unshallow` prints `count mismatches: 0`; (d) a full checkout with C-3704's `26` changed to `25` still prints `COUNT C-3704 claims 25, tools/fn_match.py prints 26` and exits 1 (the rule still bites); (e) `python3 tools/gate.py` is `4 pass, 0 fail, 0 skip`; (f) after merge the `CI quality gate` run on `main` is `success` for py3.11 and py3.13.
  - Falsifier: if a depth-1 clone with the fix still exits 1, or if the full-checkout C-3704 mutation no longer fails, the change is wrong.
  - Result: EXP-2026-11-17-H90-ci-shallow-count; C-4130–C-4137. CI was red on `main` since H85 (`c7a5529`…`3d79bcc`) because `actions/checkout` fetched only the tip: `_exp_revision` then resolved every claim to that one SHA and nine old selftest counts (`count mismatches: 9`) were measured against today's tools. A depth-1 clone reproduced 9, the same commit with full history printed 0. Fix: `fetch-depth: 0` in CI (pack is 3.2 MiB) plus `history_is_shallow` in `tools/claims_check.py` — a shallow history has no measurement revision, so the rule prints `count check: skipped (shallow clone …)` instead of guessing, and a full checkout still fails the C-3704 `26`→`25` mutation (`COUNT C-3704 claims 25 … prints 26`, exit 1). `--selftest` 25→28 checks (C-4015's number updated); gate `4 pass`.
  - Claims: C-4130–C-4139

- [x] **H86 — Make the claims half of the standing gate blocking in CI (todo half after H53)**
  - Status: done · Owner: task/h86-h86-claims-gate-blocking · Critical: no · Pair: required
  - Depends: H78 (the count rule inside `--strict`, done), H85 (the runner, done); H53 only for the second half
  - Goal: cycle 9 was planned around `ci.yml` not running `claims_check --strict`, but **H85 already closed it**: the one standing-gate step runs `tools/gate.py`, whose `claims_check` gate is `claims_check.py --strict --count-check`. So `grep -cE 'claims_check\.py --strict|todo_check\.py --strict|--count-check' .github/workflows/ci.yml` now prints `1` (the string `--count-check` inside the gate step's comment/output), and `python3 tools/claims_check.py --strict --count-check` exits `0` on `main`. This task is now the **verification + documentation** half: prove a synthetic count mismatch fails the CI step, and that `.github/workflows/README.md`'s "Hard gate" list names `tools/gate.py`. The **second half** (`todo_check --strict` blocking) stays blocked on **H53** (66 strict errors), where `prompt_qa.txt` and H85's `--board-clean` already provide the switch.
  - Precheck: `python3 tools/gate.py` → `claims_check PASS`; `python3 tools/claims_check.py --strict --count-check` exits `0`; `grep -n "Hard gate" .github/workflows/README.md` shows the old selftest/claims/todo list.
  - Scope: `.github/workflows/README.md` (the "Hard gate" contract text: name `tools/gate.py` and the PASS/FAIL/SKIP policy), and the H86 half of the CI summary wording if it still lists the three old steps. **No** workflow logic change (H85 did it) and **no** `todo_check --strict` blocking (H53).
  - Input: `.github/workflows/{ci.yml,README.md}`, EXP-2026-11-16-H85-standing-gate, H53 block.
  - Hints: the honest result here may be "H85 already did the claims half; H86 is README + a negative CI test". If the negative test needs a real red run, do it locally with the corrupt-snapshot trick (QA verified: a corrupt `image_sha256` gives `step_rc=1`, `gate: 3 pass, 1 fail`) — do not push a red PR.
  - Done when: `.github/workflows/README.md`'s gate list names `tools/gate.py` and the SKIP policy; a local reproduction of the CI step (the `PIPESTATUS` command shape) fails on a synthetic count mismatch and passes on a SKIP-only run; `python3 tools/gate.py` green; `python3 tools/todo_check.py` OK.
  - Stop: if the README's contract already names the gate (it may, after H85), mark this done as "H85 closed the claims half; README updated" with a one-line Result and leave the todo half to H53's follow-up.
  - Claims: C-4090–C-4099
  - Result: EXP-2026-11-21-H86-claims-gate-blocking (C-4090, C-4091): H85 already made the claims half blocking (ci.yml runs gate.py | tee PIPESTATUS[0], claims gate = claims_check --strict --count-check); README Hard gate names tools/gate.py + SKIP policy; new tools/ci_gate_repro.py --selftest (PASS) proves a synthetic count mismatch fails and SKIP-only stays 0; gate.py 4 pass/0 fail/0 skip; todo half stays on H53

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

- [x] **M1.20 — `pdata.py`: the function table of every module, and `fn` labels that come from it**
  - Status: done · Owner: task/m1.20-pdata-all · Critical: yes
  - Result: EXP-2026-11-17-M1.20-pdata-all; C-3510–C-3519 registered. `pdata.py census` gives every module a record count and an ASCII totals line with the with/without split — A `149 modules, 149 with pdata, 0 without (NO-PDATA), 0 errors, 87530 records`; B `91 … 91 … 0 … 0 … 21930`; C `88 … 88 … 0 … 0 … 25243` — while `NO-PDATA` stays reserved for e32 `(0, 0)` and a decode/sort fault is `ERROR` + exit 2; `pdata.py where --try-index` shows the index is not the locator (sec2 pick `UNSORTED`, exact-RVA sec3 `sorted`) for the 1 (A) / 10 (B) / 3 (C) modules whose table is outside sec2; the four `sh4xref --to` spot checks print the pdata holders (`0x0041c7dc`→`0x0041c990`, `0x004125a8`→`0x00413a6c`, `0x00542250`→`0x0054232c`, `0x0032ef60`→`0x0032edd0`) with no wire-up change needed; selftest 45 checks, `OK (0 failed)`.
  - Note (M1.23 merge, 2026-11-15): the wire-up gap the blocker named is closed — `cerom.e32()` has `exception`, `sh4xref`/`sh4scan`/`reader_precheck` use pdata, and C-3610–C-3619 register the claims (EXP-2026-11-15-M1.23-pdata-wireup). This task re-opens for its own Done-when: `pdata.py table` count for every module, `gaps`, and the selftest coverage.
  - Blocker (SE 2026-11-13): the tool is real (`pdata.py` gives 7,596 `Navi.exe` records, selftest PASS) but the EXP's claimed wire-ups are absent from `777fb68`: `cerom.e32()` has no `exception` key, `sh4xref.py`/`sh4scan.py`/`reader_precheck.py` contain 0 `pdata` references, and C-3510–C-3519 were never added to `claims.md`. The done-when needs pdata-backed `fn` labels, which do not exist yet.
  - Unblock: M1.23 (wire-up + register the corrected C-351x claims) — merged; re-opened per rule 15
  - Depends: — (H51; faster after M1.19's cache)
  - Goal: every tool that prints `fn 0x…` takes the start from the module's `.pdata` instead of guessing it from a prologue pattern.
  - Precheck: `python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe 0x004125a8` prints `START … length 0x12c`.
  - Scope: new `tools/pdata.py` (`--selftest`; `table IMG --module M [--json]`, `fn IMG --module M VA…`, `gaps IMG --module M` = executable ranges with no record); find the pdata section per module from the e32 header's exception-directory entry rather than "the last compressed section" (H51 used index 2 for `Navi.exe` because it is the only read-only compressed section); `sh4xref.py`, `sh4scan.py`, `reader_precheck.py` use the table when the image is given. All 149 modules of build A, plus build B/C.
  - Input: record layout verified on `Navi.exe` by H51: 8 bytes, `u32 begin`, `u32` with bits 0–7 prologue length and bits 8–29 function length (both in 2-byte instructions), bit 30/31 flags; 7,596 records, sorted, first `0x0032ed9c`, last ends `0x00558300`. Sec0 below `0x0032ed9c` holds no function (strings and constants, e.g. `LCTBL001.DAT` at `0x0017a1f8`). `tools/cerom.py` `e32()` gives the directory table.
  - Hints: `nk_decomp.parse_pdata`/`locate` are a starting point. A module whose pdata is in an uncompressed section needs no decompression at all — check `OSMDLL.dll`, `MAL_DataVol.dll`, `NaviMapCC.dll` first, they are the map modules. Leaf functions have no record (`GAP`): list gaps longer than 8 bytes that are the target of a `jsr`/`bsr` and call them `leaf`.
  - Done when: `pdata.py table` gives a record count for every module with a pdata directory (counts in the EXP); `sh4xref --to 0x0041c7dc` and three other spot checks print the pdata start; the selftest covers `START/INSIDE/GAP` and an unsorted table (must fail loudly).
  - Stop: a module with no exception directory is listed as such, not guessed.
  - Claims: C-3510–C-3519


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


- [x] **H103 — `cardcheck` cannot check a tree we built: no `--generate-fixture`, so L1 can never be a CI row**
  - Status: done · Owner: task/h103-cardcheck-fixture · Critical: yes · Pair: required
  - Depends: H26 (the registry); H40 calls it — this task is the primitive only, not the L1 row
  - Goal: retro 2026-11-18 action 3 closes H40, but H40 cannot start from zero: `cardcheck.py` only accepts `--image` (7.5 GB vendor card) or `--root` (a vendor-extracted tree), and the one no-vendor builder we have, `one_tile_pipeline.py --synthetic`, produces a tree QA measured at `cardcheck rc=1` (section 2 levels 2/4/5 and section 4 level 1 not in `MMAIN` — 2026-11-17-1851-53-qa.log, H40's Input). So on CI there is nothing to point `--root` at, and the L1 row stays NOT COVERED forever. A tiny in-process tree that `cardcheck` *accepts* is a ~200-line deterministic builder, not an OSM run; making it a `cardcheck` mode (not a second tool) keeps one validator and one exit code.
  - Precheck: `python3 tools/cardcheck.py --help | grep -c generate-fixture` prints `0`; `grep -n 'add_argument("--image"\|add_argument("--root"' tools/cardcheck.py` shows the two source flags and nothing that builds a tree; `python3 tools/one_tile_pipeline.py --selftest` prints the synthetic path's honest `cardcheck` line (not PASS).
  - Scope: `tools/cardcheck.py` only — `--generate-fixture DIR` / `--fixture-in-process` that writes and then validates the tree in the same run: MBR+TFAT16 layout, FAT32 root, `DRSTR001.DAT` + `MMAIN001.DAT` + `CMP.LST` + one `MAPAL001/BxxRyyR.DAT` with level/dir tables that agree with `MMAIN`, `REFER001` pairs only if written, and every level/box/header value derived from `mmain.py`/`drstr_ze0.py`/`tilewriter.py`, never hand-typed. Exclusion: no OSM input, no vendor bytes, no tile *content* semantics (an empty road set is fine if `cardcheck` accepts it), no `--image` path change.
  - Input: `tools/cardcheck.py` (checked rows and `--partial/--fast`), `tools/mkcard.py`, `tools/drstr_ze0.py`, `tools/mmain.py`, `tools/tilewriter.py`, `tools/one_tile_pipeline.py` (`build_synthetic_out`, the rc=1 tree), H40's Input line.
  - Hints: keep the builder incremental — add one file at a time and let `cardcheck` name each new disagreement (the M5.33 tree's failures are the list to satisfy one by one). Print `fixture=none` in the JSON so a vendor run can never be mistaken for a fixture run. If a check genuinely cannot be satisfied without vendor semantics, `--generate-fixture` must report that check as SKIP with the reason, and the task's Done-when lowers to "the remaining FAILs are named", never to a fake PASS.
  - Done when: `python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h103-tree --json /tmp/opencode/h103.json` exits 0 and the JSON names every check PASS/SKIP with `fixture=none` absent; the tree is byte-identical across two runs (`sha256sum` of a sorted file list matches, timestamps fixed); `--selftest` runs it in a temp dir; `python3 tools/selftest.py --only cardcheck` PASS.
  - Stop: if `cardcheck` turns out to require a real FAT32 geometry that cannot be produced deterministically in-process, split the builder into a committed tree under `tools/fixtures/` (a few KiB, `git add -f` under AGENTS' tiny-fixture rule) and keep `--root` as the only invocation; block the `--generate-fixture` half with the measured reason.
  - Falsifier: `cardcheck --generate-fixture` does not exist, so no L1 row can read a tree that no vendor produced.
  - Claims: C-4340–C-4349
  - Result: EXP-2026-11-20-H103-cardcheck-fixture. `tools/cardcheck.py` gains `--generate-fixture DIR` (writes a no-vendor tree from `ze0_tile_header`/`tilewriter`/`drstr_ze0`/`cmpind_writer` and validates it in the same run) and `--selftest` (temp dir, no vendor data). Done-when passes: `--generate-fixture /tmp/opencode/h103-tree --json …` exits 0, `ok=true`, `counts={"pass":6,"fail":0,"skip":2}`, `fixture=none` in the JSON, six PASS (`tree`,`headers`,`cmp`,`drstr`,`mmain`,`version`) and `mbr`/`fat` SKIP with a reason; two runs are byte-identical on one interpreter; `--selftest` 18/18 ok and `selftest.py --only cardcheck` PASS. The byte-identity is per interpreter only (zlib-ng vs stock zlib change the tile and REFER `.cmp`/`.ind` bytes, not the verdicts). `--root`/`--image` behavior unchanged. H40 (CI row), H104 (baseline) and H105 (breaks) stay their own blocks.

- [ ] **H104 — `cardcheck` has no committed baseline: a green L1 can silently lose a check**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H103 (the fixture it pins); H57 is the L2 half and stays its own task
  - Goal: H57 asks for "a committed no-vendor baseline and a documented PASS->FAIL gate"; L1 has neither, so a tree that passes today can pass tomorrow with one check silently SKIPped or dropped from the checker. `cardcheck --json` already carries per-check rows, so the baseline is a small committed JSON keyed by *check id* (rule: stable key, never a line or an index) plus a diff that names a check that disappeared, changed PASS→SKIP, or changed SKIP→FAIL.
  - Precheck: `python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h104-tree --json /tmp/opencode/h104.json` (after H103) writes a per-check report; `grep -c baseline tools/cardcheck.py` prints `0`.
  - Scope: `tools/cardcheck.py` only — `--baseline PATH` (compare, exit 1 on a lost PASS, a new FAIL, or a vanished check; a new SKIP is reported and is *not* a loss) and `--update-baseline PATH` (refuse without an EXP path in the commit message? no — just print the diff and require the file to be staged). New committed file `tools/fixtures/cardcheck_baseline.json` (ids + expected statuses only, no vendor bytes). Exclusion: no change to what any check asserts, no golden tile bytes.
  - Input: `tools/cardcheck.py` (`--json` schema, check ids), H103, H57's block (`PASS->FAIL` wording), `tools/l1l2_fixtures.py` (its `NOT COVERED` vocabulary, for consistency).
  - Hints: a vanished check id must be a failure — that is the silent-loss case ("we dropped the REFER001 row"). Key by the check's stable name the JSON prints today, not by order. `--update-baseline` must print exactly which rows moved and why, so a reviewer can see a status relaxation in the diff.
  - Done when: baseline committed; `python3 tools/cardcheck.py --generate-fixture … --baseline tools/fixtures/cardcheck_baseline.json --json …` exits 0 on `main`; with one check renamed (temp edit) it exits 1 with `BASELINE LOST <id>`; with one expected PASS forced to SKIP it exits 1; `--selftest` covers both negatives; `selftest.py --only cardcheck` PASS.
  - Stop: if the check id set is not stable across `--partial`/`--fast`, record that in the baseline header and pin the baseline to the exact flag set it was measured with; do not make the id a hash of the message (it changes with wording).
  - Falsifier: a cardcheck run whose JSON omits a check today reported, compared against a committed baseline, still exits 0.
  - Claims: C-4350–C-4359

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

- [ ] **H107 — `l3check --build-corpus` says "runnable 1/7" while two of the seven are blocked only on a missing argument**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H96 (the verdict/baseline contract); H43 (generated corpus) is separate
  - Goal: the L3 number every log quotes (`pass=1 … blocked=6 runnable=1/7`) reads as "one reader works, six are unwritten". In fact `cmp_ind_reader` and `cmp_ind_reader_us2011` print `BLOCKED … needs --image/--cmp/--ind (not provided in corpus-only run)`: they are blocked *by the invocation*, not by missing firmware work, and with `--cmp` one of them is a runnable fragment. A summary that splits those buckets stops the map number from reading three kinds of "not done" as one.
  - Precheck: `python3 tools/l3check.py --build-corpus | grep 'needs --image'` prints the two shared-path rows; the summary line prints one `blocked=6` that contains them, the four reader gaps and `mapcode_comparator` (retired).
  - Scope: `tools/l3check.py` only — the summary and `RESULT:` line gain `blocked=6 (2 need an argument, 4 reader gaps)` and the JSON gains `blocked_reason` per target; exit codes unchanged (H96 owns the baseline, do not touch it). Exclusion: no corpus download in CI, no change to any target's status.
  - Input: `tools/l3check.py` (the `RESULT:` block, `counts`, the per-target messages), `tools/l3_harness/targets.json`, H96's block.
  - Hints: derive the split from the target's own message/kind (`firmware_call` needing `--cmp`) rather than a hard-coded name list, so a new shared-path target lands in the right bucket. Do not let the split become a *pass* for the argument case — `runnable` stays the honest count.
  - Done when: the corpus run prints the split; `--json` carries it (`blocked_reason` per target, additive); `--selftest` asserts the split on the existing fixture; `python3 tools/l3check.py --build-corpus` still exits 0 and `runnable=1/7` remains the quoted number.
  - Stop: if the message is the only signal and it is unstable, make the split a field in `targets.json` (`needs:`), which is the stable key, and say so in the EXP.
  - Falsifier: the summary keeps one `blocked=6` number and no row says why each target is blocked.
  - Claims: C-4380–C-4389

- [ ] **H108 — the QA CI check is prose: nothing proves the tip run is green, or that a green job hides a red step**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: H98 (the enforcement half); this task is only the audit command
  - Goal: `prompt_qa.txt` tells QA to run `gh run list --branch main` and `gh pr checks` and to report red runs; that is manual, per-pass, and a green-looking job can hold a failed step (H90's class). Cycle 14 cost a 20-run JSON read to distinguish five `cancelled` pushes from red ones. One command that prints (a) the tip's SHA, (b) every workflow's result *for that SHA*, (c) any job whose steps are not all success, and (d) the `cancelled` rows as informational (they are the concurrency de-dup, green replacement exists) makes the per-pass answer mechanical and hard to skip.
  - Precheck: `grep -rn 'gh run list' dev_process/*.log | wc -l` is what exists today — the number is re-derived by hand each pass; no `tools/` file runs it.
  - Scope: new `tools/ci_audit.py` (`--workflow`, `--branch`, `--repo`, `--json`, `--selftest`) using `gh` via subprocess, plus the QA prompt's one-line invocation. Exit 0 when the tip is green in every workflow and every job's steps are success; exit 1 when the tip has a non-success run or a green job has a non-success step; `--require-tip <sha>` for the pre-push case. Exclusion: no token handling, no API writes, no network in `--selftest` (a committed JSON fixture stands in for `gh` output).
  - Input: `.github/workflows/{ci.yml,l1l2-fixtures.yml}` (job names), `gh run list --json …` shape (already used in the QA logs), H90's EXP (the 12 red pushes), `prompt_qa.txt` §"Check the runs".
  - Hints: a `cancelled` run is only OK when a *later* SHA of the same workflow succeeded *and* the tip itself is green — otherwise a cancelled tip is a gap, not a de-dup. Print the HTTP/runs count so an empty list is visibly "0 runs", never "green".
  - Done when: `python3 tools/ci_audit.py --branch main` exits 0 on today's tip and prints the tip SHA + per-workflow result + `cancelled 5 (superseded)`; run against a fixture whose job has one failed step it exits 1 naming the step; against a fixture whose tip run is missing it exits 1; `--selftest` covers all three; `python3 tools/selftest.py --only ci_audit` PASS.
  - Stop: if `gh` is unavailable on CI, keep it local/QA-only (it is a role tool) and say so in the docstring; do not add it to `gate.py`.
  - Claims: C-4390–C-4399

- [ ] **H111 — `claims_check --prose-counts` is an opt-in flag: the standing gate does not run it**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H92 (the mode, `--selftest` cases and the off-by-default decision), H78 (`--count-check` is in `gate.py`), H90 (the shallow-history skip)
  - Goal: H92 ships `--prose-counts` but leaves it off: `grep -c 'prose-counts' tools/gate.py` prints `0`, so `tools/gate.py` cannot fail on a stale quoted count (H87's `stays 12` class). Turning the rule into a standing gate needs the unmeasurable rows resolved first: C-927 and C-1023 say `stays N` with no allowlisted command and no cell selftest, so the mode skips them and the gate would be green while they stay unmeasured (C-4171's `stays `0xfdb6`` is a hex offset and no shape at all).
  - Precheck: `grep -c 'prose-counts' tools/gate.py` prints `0`; `python3 tools/claims_check.py --prose-counts` prints `census: rows 2252 prints ['C-3740', 'C-4156'] stays ['C-927', 'C-1023'] footer []` and `stale prose counts: 0` — two measurable `prints` shapes (C-3740 measured, C-4156 unmeasured: it has no revision), two unmeasured.
  - Scope: `tools/gate.py` only (one `Gate` or one flag on the `claims_check` argv) plus the `gate.py --selftest` cases; the C-927/C-1023 rows are pinned to a revision and a command by whoever owns their claims (a separate record pass), not by this task. No new tool; no `claims_check.py` change unless the allowlist must grow.
  - Input: `tools/gate.py` (`standing_gate`, `--selftest`), `tools/claims_check.py` (`--prose-counts`, `prose_count_problems`, `census`), H92's EXP, C-927/C-1023/C-4171 rows.
  - Hints: gate `--prose-counts` must run on the full history (H90's shallow skip is already in `main()`), and a C-927-style unmeasurable row must not fail the gate — the mode skips it by design; say so in the docstring. If the rows stay unmeasured, the honest gate is `--prose-counts` plus a printed census, not a silent pass.
  - Done when: `tools/gate.py` runs `claims_check --prose-counts`; `gate.py --selftest` proves a seeded stale `prints N` row gives `FAIL exit 1` and a clean ledger `PASS`; the real `python3 tools/gate.py` prints `gate: 4 pass, 0 fail, 0 skip`; the C-927/C-1023 rows are either measured or listed in the gate output as skipped.
  - Falsifier: with `--prose-counts` wired in, a seeded stale count is still `gate: … 0 fail` (the rule does not bite), or a clean ledger turns the gate red.
  - Claims: C-4490–C-4499

- [x] **H115 — `TODO.md` open-block citations are not fence-aware: the fenced task template counts as an open block**
  - Status: done · Owner: task/h115-fn-audit-fence · Critical: no · Pair: required
  - Depends: H77 (`fn_audit.fenced_lines`)
  - Goal: H77 made the docs-base and EXP scans skip fenced code, but `fn_audit._open_blocks`/`citations_open_tasks` (the l3 open-block scan) still read `TODO.md` line by line, and `TODO.md` has fences (the task-field template at about line 208, others near 307 and 927). The fenced template's `- [ ] **ID — title**` line is parsed as a real open block (pre-existing bug), so any `0x…` quoted in a fenced example under an open task becomes a live l3 citation.
  - Precheck: `grep -n '^```' TODO.md` lists the fences; `python3 tools/fn_audit.py archive/head256.img --scope l3` prints `open blocks N`; record N and whether the template block is among them.
  - Scope: `tools/fn_audit.py` (`_open_blocks`, `citations_open_tasks`) plus `--selftest` cases; re-freeze `docs/research/fn-audit-l3-corpus-2026-11-20.json` if rows change. No `TODO.md` text edit.
  - Done when: a fenced `- [ ] **H999` template is not an open block and a fenced `0x…` under a real open block is not cited (selftest), the unfenced controls still are; the EXP records the open-block count before/after on the real board; `python3 tools/gate.py` stays green.
  - Stop: if the board's fences are unbalanced (an unclosed fence hides nothing, per H77), record the lines and ship only the template fix.
  - Claims: C-5720–C-5729
  - Result: `docs/experiments/EXP-2026-11-20-H115-fn-audit-fence.md` (C-5720–C-5723). `fn_audit._open_blocks` now derives `fenced_lines` and ignores a fenced header/boundary (the line-209 template is no longer a block); `citations_open_tasks` skips fenced lines. Real board open blocks `116 → 115` at base `2e683be` (`115 → 114` after the `3d263f9` rebase; contributing/citation lines unchanged by the fix); frozen corpora keep identity (`0 new / 0 gone`, 1076 l3 / 521 docs rows, line-only drift, no re-freeze). Negative control: a `fn 0x004125a8` fenced in the H115 block is cited by the old code at `TODO.md:1428` and not by the fix. `fn_audit --selftest` `OK (99 checks, 0 failed)`; `gate.py` `4 pass, 0 fail, 0 skip`.

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

- [x] **M1.36 — Module census of the CE ROMs on four cards (EU 2011, US 2011, EU 2014, EU 2016)**
  - Status: done · Owner: claude/project-thread-64ftoc · Critical: no · Pair: solo
  - Depends: —
  - Goal: first answer to "what differs between the binaries of the card generations".
  - Done when: an EXP has the module counts, added/removed modules and code sizes per image.
  - Result: EXP-2026-11-20-M1.36-module-census-4-images (C-6280–C-6285): same five-segment SH-4 layout on all four; EU 2011 and US 2011 share kernels B/C byte for byte and differ only in A; 2014/2016 are platform `X212` with different kernels (`FlashManager2`, `fmmdrv_05/07`); `Audio.exe` +54 %, `Navi.exe` +4 % in 2014.
  - Claims: C-6280–C-6289

- [x] **M1.36b — `tools/rom_atlas.py`: one table of every module on every card image (the binary and data atlas)**
  - Status: done · Owner: task/m1.36b-rom-atlas · Critical: no · Pair: solo
  - Depends: M1.36 (done), M1.22b (`fn_match`, reloc-masked function hashes, done)
  - Goal: a committed, reproducible map of what is on a card: per image and ROM (A/B/C) every module with size, sections, reloc-masked code hash, imports/exports, COM class names and its role in one line; plus the data side (FAT tree families, TFAT16 tail, `FILESentry` files). M1.36 was a scratch script whose hashes include XIP relocation.
  - Precheck: `python3 tools/fetch_image.py --image EU2014 --part 256M -o X` verifies the size; `python3 tools/cerom.py --image-start 0x200200 X modules` lists 153 modules.
  - Scope: the four pinned images; output `docs/research/rom-atlas.md` (generated, with the command) + `--json`. Role lines only where a string/export supports them, else `unknown`. Pin the EU2014/EU2016 256M SHA-256 in `fetch_image.py`.
  - Done when: `rom_atlas.py --selftest` passes; the table reproduces M1.36's counts; for EU 2011 vs US 2011 it reports which A modules are equal after reloc masking (negative control: B/C all equal, C-6281).
  - Claims: C-6290–C-6299
  - Result: EXP-2026-11-21-M1.36b-rom-atlas; census reproduced (A 149/151/153/153, B 91/91/95/96, C 88/88/92/92); EU2011 vs US2011 A equal 1 (atlce400.dll) with B 91/91, C 88/88 negative control; raw==masked equal on all 9 pairxROM rows (0 gained); C-6290-C-6299

- [x] **M1.37 — Changelog between builds, module by module (functions, strings, exports)**
  - Status: done · Owner: task/m1.37-rom-changelog · Critical: no · Pair: solo
  - Depends: M1.36b
  - Goal: for each module present in two builds: functions added / removed / changed (pdata + `fn_match`), new strings, new exports and COM methods; first for `Navi.exe`, `Audio.exe`, `BT_MGR.dll`/`BT_ENG.dll`/`BT_FW.dll`, `Speech.exe`, `DriveComputerCC.dll`, pairs EU2011→EU2014 and EU2014→EU2016. This is what tells whether a newer Bluetooth or navigation build has anything we want.
  - Precheck: `python3 tools/pdata.py` lists functions for `BT_MGR.dll` on both images; `fn_match` reaches ≥ 90 % on a module known to be nearly equal (`BT_FW.dll`, same size in all four).
  - Scope: static diff only; one EXP per module group with counts and the 20 largest changed functions named by their strings. No behaviour claims without a string or an L3 run.
  - Done when: `docs/research/rom-changelog.md` has the per-module table for the two pairs, with a control (EU2011 vs US2011 B = 0 changes).
  - Stop: a module whose match rate is < 50 % is reported as `rewritten`, not diffed by hand.
  - Claims: C-6300–C-6309
  - Result: EXP-2026-11-22-M1.37-rom-changelog; per-module tables for EU2011->EU2014 and EU2014->EU2016 in docs/research/rom-changelog.md; control EU2011 vs US2011 build B = 0 changes; BT_FW.dll 100%; C-6300-C-6309

- [ ] **M1.38 — Can a 2014/2016 kernel ROM start on the 2011 board? (static)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M1.36 (done); M6.19 helps (what the unit's own flash holds)
  - Goal: decide whether "use the newer binaries" is possible at all on Marek's `QY7200ND`: compare ROMHDR RAM windows, BSP/platform strings, the driver set (`fmmdrv` vs `fmmdrv_05`/`_07`, `FlashManager` vs `FlashManager2`, LCD, SDHC) and the launcher's unit checks between `X210` and `X212` builds B.
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 <EU2014 head> romhdr` prints a ROMHDR.
  - Scope: static, builds B/C of EU2011 and EU2014. Output: a table check → 2011 → 2014 → compatible / not / unknown, and one verdict. No card is built.
  - Done when: the EXP names at least the flash-driver selection rule (how `fmmdrv_05`/`_07` is chosen) or records it as unknown with the VA where the choice is made.
  - Claims: C-6310–C-6319

- [x] **M1.39 — Hardware map of the head unit: CPU, RAM, flash, serial ports, buses (from the firmware)**
  - Status: done · Owner: claude/project-thread-64ftoc · Critical: no · Pair: solo
  - Depends: —
  - Goal: Marek's question "what CPU, how much RAM and flash, what is connected to which I/O" answered in one page under `docs/hardware/`.
  - Done when: `docs/hardware/head-unit.md` exists with a status per row and an EXP behind it.
  - Result: EXP-2026-11-20-M1.39-hardware-map (C-6410–C-6416), page [`docs/hardware/head-unit.md`](docs/hardware/head-unit.md): SH-4A (SH-NaviJ family, part unproven), DRAM from `0x08000000`, at least 102 MiB (128 MiB guessed), 44.6 MiB for applications; 8 MiB NOR flash; 800 × 480 × 16 bpp; port users from device-name strings — `SCI1:` audio microcontroller, `SCI3:` display, `SCI6:` debug console (= kernel debug SCIF `0xffe46000`), `SCI7:` GPS, `SCI8:` Bluetooth, `UAT3:` CAN sub-microcontroller; `0xffe70000` is the USB host block (OHCI at `+0x400`).
  - Claims: C-6410–C-6419

- [x] **M1.40 — Hardware map II: I2C slaves, GPIO pin roles, baud rates, the users of `SCI0:` and `UAT4:`**
  - Status: done · Owner: task/m1.40-hw-map-ii · Critical: no · Pair: solo
  - Depends: M1.39 (done)
  - Goal: fill the rows `docs/hardware/head-unit.md` leaves open, still from the firmware: which I2C slave addresses each driver uses on which bus (and what chip that suggests), which GPIO bits `GPIO.dll` clients set or read and for what (mute, SD power, card detect, LCD power, reverse, illumination), the baud rate and framing each port user sets (`SetCommState` DCB), and who opens `SCI0:` / `UAT4:` (compressed sections were not searched in M1.39).
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 IMG256 exports I2C.dll` and `… exports GPIO.dll` print the driver entry points; `python3 tools/nk_decomp.py` decompresses a `.data` section of `SDHC.dll`.
  - Scope: static, build B (+ A for clients), EU2011 = US2011 for B. For each client: the `DeviceIoControl` code and the constant arguments at the call site (`tools/sh4xref.py`, `callgraph.py`); decompress `.data` sections before the string search. Update `docs/hardware/head-unit.md` and the peripheral table of `docs/research/full-system-emulation.md`.
  - Hints: the debug shell on `SCI6:` (C-6414) is the most useful row for bench work: its baud rate and command list tell what a serial adapter on that pin would give. `0xffe70808` (C-6415) is worth one look in `UsbOhci.dll` for the register name.
  - Done when: the page has ≥ 5 I2C (bus, address, driver) rows or the reason they cannot be read statically, a GPIO table with ≥ 8 named bits, and baud rates for `SCI1:`, `SCI6:`, `SCI7:`, `SCI8:`, `UAT3:`.
  - Stop: chip names stay HYPOTHESIS without a board photo; do not guess a part from an address alone.
  - Claims: C-6420–C-6429
  - Result: EXP-2026-11-22-M1.40-hw-map-ii; head-unit.md updated with I2C/GPIO/baud/SCI0/UAT4 static map; C-6420-C-6429

- [ ] **M1.41 — Decompile map of the Bluetooth stack, and why two phones work badly**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M1.36b/M1.37 help: the same modules in the 2014/2016 builds)
  - Goal: side track, not on the map path. Modules: `BT_FW.dll` (B), `BT_MGR.dll`, `BT_ENG.dll`, `BT_WRPENG.dll`, `BT_DB.dll`, `BT_Modem.dll`, `PhoneBTA.exe`, `PhoneCC.dll`, `BtAudioCC.dll` (A). Answer: (1) what each module does and how they call each other; (2) the data model for paired devices — how many can be stored, how many can be connected at once, per profile (HFP, A2DP/AVRCP, PBAP, DUN); (3) where the limit that hurts with two phones is: a constant in the unit's code (patchable), the reconnect policy (which phone wins at start), or the Bluetooth module's own firmware (`BtUpdate.exe` payload, not patchable by us); (4) whether the 2014/2016 builds changed any of this.
  - Precheck: `python3 tools/pdata.py` lists functions for `BT_MGR.dll`; `python3 tools/cerom.py --image-start 0x200200 IMG256 exports BT_ENG.dll` prints exports.
  - Scope: static (strings, exports, `callgraph.py`, `sh4dis.py`; Ghidra from M9.2 if a non-Claude runner has it). Output `docs/firmware/bluetooth.md` in the common template of `docs/firmware/README.md`: module table, feature list, call graph between modules, the device-table layout, and a "what could be changed" list with the VA of each constant. No patch is built.
  - Hints: the registry starts nine `BT_MGR.dll` device instances `BTA1:`–`BTA9:` and the module talks to the radio on `SCI8:` (EXP-2026-11-20-M1.39); `BT_FW.dll` has the same size in all four builds (M1.36), so the stack above it is where builds differ.
  - Done when: the page states the maximum paired and simultaneously connected devices with the code evidence (VA, constant), and one verdict for two-phone support: `patchable constant / policy in code / module firmware / unknown`.
  - Stop: if the connection limit is enforced inside the Bluetooth module (HCI error from the module, not a check in our code), say so and close the patch idea.
  - Claims: C-6430–C-6439

- [ ] **M1.42 — Decompile map of the audio stack (`Audio.exe`, `anwdrv`, `wavessi`, `DspDrv`, `MuteDrv`, `BeepDrv`)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M4.60 is the data side: where the sounds are)
  - Goal: side track. What the SH-4 does itself and what it only asks the audio microcontroller to do over `SCI1:`: source switching, volume, mixing of guidance over media, USB/iPod/Bluetooth audio path, radio. List the message set of the `anwdrv` protocol (device `AUD`/`TNR`/`TMC`/`UPD`…: command ids, lengths).
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 IMG256 exports anwdrv.dll` prints exports.
  - Scope: static, EU2011; compare sizes with EU2014 (`Audio.exe` +54 %, M1.36). Output `docs/firmware/audio.md` (template: `docs/firmware/README.md`).
  - Done when: the page has the audio path diagram (who produces PCM, on which SSI, who mixes) and ≥ 20 `anwdrv` messages with direction and meaning or `unknown`.
  - Stop: the microcontroller's own firmware (`AudioMiconUpdate.exe` payload, V850) is out of scope.
  - Claims: C-6440–C-6449

- [x] **M1.43 — Decompile map of the vehicle screens (`Vehicle.exe`, `DriveComputerCC`, `EvTimerCC`, `EvNoticeCC`, `HvacCC`, `ComfortCC`)**
  - Status: done · Owner: task/m1.43-vehicle-signals · Critical: no · Pair: solo
  - Depends: —
  - Goal: side track. Which CAN signals reach the SH-4 (through `CAN.dll` on `UAT3:`), in what units and resolution, and what the drive computer does with them: is energy shown rounded from a finer value (so a finer display or other aggregates are a UI change), or does the coarse value arrive already rounded.
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 IMG256 exports CAN.dll` prints exports.
  - Scope: static, EU2011. Output `docs/firmware/vehicle.md`: signal table (id, name from strings, scale if a multiply/divide is visible, consumer module), the formulas of the drive computer screens.
  - Done when: ≥ 10 signals with consumer and unit, and for the energy economy value the VA where it is scaled for display.
  - Stop: do not send anything to a car; this task is read-only knowledge.
  - Claims: C-6450–C-6459
  - Result: EXP-2026-11-21-M1.43-vehicle-signals; 17 VCAN frames mapped, 10 with consumer+unit/flag/enum (Done-when 10>=10; 7 raw/unknown); energy-economy scaled for display at DriveComputerCC fn 0x02518f58, halfword 0xf463 fdiv FR6,FR4 @0x02519072

- [x] **M1.44 — Decompile map of the camera path (`CameraCC.dll`, `VIN.dll`)**
  - Status: done · Owner: task/m1.44-camera-ioctl · Critical: no · Pair: solo
  - Depends: —
  - Goal: side track. How the reversing camera image gets to the screen (video input driver, overlay of guide lines), what triggers it (reverse signal over CAN or GPIO), and whether the input can be shown on demand.
  - Scope: static, EU2011. Output `docs/firmware/camera.md` (template: `docs/firmware/README.md`).
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 IMG256 exports VIN.dll` prints exports.
  - Done when: the page names the trigger (signal and VA of the check) and the IOCTLs `CameraCC` sends to `VIN1:`.
  - Stop: static only; nothing is tried in a car.
  - Claims: C-6460–C-6469
  - Result: EXP-2026-11-21-M1.44-camera-ioctl; Done-when met with correction: trigger EVENT_NAV_SENSOR_BACK navdrv fn 0x039e3a34 (raised from sensor bit 0 in fn 0x039e6690); the eight VIN1:/CEN1: IOCTLs are sent by SystemCC.dll (0x80062000/04/08/14/18/1c, 0x800d2044/54), not CameraCC.dll

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

- [ ] **M1.46 — Subsystem map of `Navi.exe`: what a rewrite or a port would have to replace**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (uses the reader work of M3 and the call graph)
  - Goal: side track, the base for Marek's "rewrite Navi in modern code" idea and for "is the 2014 `Navi.exe` faster". Split the 10 MB of `Navi.exe` and its `Navi*CC`/`Navi*DLL` modules into subsystems (map data access, rendering, search, route calculation, guidance, positioning, traffic, UI glue, IPC) with function counts and code size each, and the interfaces between them (COM classes, message ids, exported C APIs).
  - Precheck: `python3 tools/callgraph.py` builds the graph for `Navi.exe` (US2011 or EU2011) and `python3 tools/pdata.py` gives the function list.
  - Scope: static. Cluster by call graph + strings + known reader VAs (`docs/research/reader-coverage.md`); output `docs/firmware/navi-subsystems.md` with the table and a diagram, and a list of the external interfaces a replacement process would have to speak (who starts Navi, which messages the HMI sends it).
  - Done when: ≥ 80 % of `Navi.exe` code bytes are assigned to a named subsystem or to `unknown`, and the route-calculation subsystem's entry points are listed (ties to M9.56).
  - Stop: this is a map, not a rewrite; do not start re-implementing.
  - Claims: C-6480–C-6489

- [ ] **M1.48 — Decompile map of the antitheft (IMMO / "SECURE" screen) path**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M6.19 helps: the PROD record of a real unit)
  - Goal: side track, but it matters for bench work: a unit moved to another car, or powered on a bench without the car's CAN, can show the SECURE screen. Say who decides (the audio microcontroller, the SH-4, or the car's BCM), what is compared (PROD `+0xA0` 4-byte IMMO code, flag `+0x193`; LeafSDTools "DISABLE IMMO" zeroes the flag), over which link, and what stays blocked while locked.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 exports AntitheftCC.dll` prints exports; the string `ANT_RCV_SECURITY_LOCK` is found in `anwdrv.dll`.
  - Scope: static, EU2011 = US2011 for build B. Modules: `anwdrv.dll` (device `ANT1:` on `SCI1:`), `\windows\AntiTheft.exe` (started by `AppLaunch.dll`), `AntitheftCC.dll` + wrapper, the `CApi_AntitheftUnlock` / `CApi_AntitheftRcvSecure` API, and the waiters on the `ANTITHEFT_UNLOCKOK` event. Output `docs/firmware/antitheft.md` (template: `docs/firmware/README.md`) with the message sequence.
  - Hints (strings seen 2026-11-21, US256, not decompiled): the audio microcontroller side reports `ANT_RCV_SECURITY_LOCK` / `ANT_RCV_SECURITY_RELEASE_OK`, the SH-4 answers `ANT_SEND_SEC_RESPONSE` / `ANT_SEND_SEC_RELEASE`; the updater (`CUpManager::AntiTheftThreadMain`), `Audio.exe` (`CAudioAccessFunction::AntitheftFunc`), telematics (`dcc_AntiTheftProc`), USB (`UsbAntiTheftProc`) and `Vehicle.exe` (`[VCL]Antitheft Lock...`) each run a thread that waits for the unlock; the HMI has `SRT_COLD_SECURE` / `POP_SRT_COLD_ANTI_THIEF_SECURE` screens and status pairs `…_FNR_…` / `…_CAS_…` (two vehicle variants). Marek's unit has the flag at 0 and code `FF FF FF FF` (C-5202).
  - Done when: the page has the lock and the release sequence with the VA of each send/receive, names where the code comparison happens (or shows it is not in SH-4 code), and lists what each waiting process refuses while locked.
  - Stop: no code or PROD bytes of a real unit are committed; do not describe how to defeat the lock on a unit that is not one's own beyond what LeafSDTools already documents.
  - Claims: C-6730–C-6739

- [ ] **M1.49 — Polish in the user interface: where the UI texts live and what adding a language would take**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: research
  - Depends: —
  - Goal: Side track Marek will ask about once the map is Polish: menus and voice are not. Find the UI string resources (module, format, encoding, per-language tables), how a language is selected, and whether the language list is fixed in code.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all Deutsch Français` finds the language names; `python3 tools/lang_code_table.py --help` works.
  - Scope: EU2011 static: resource container, string count per language, the language list and its consumers, fonts used by the UI (shares the glyph question with M4.87), the EU2014 card's language set for comparison.
  - Input: `tools/lang_code_table.py`, `tools/skn_info.py`, `tools/ce_strfind.py`, `docs/format/skins.md`, EXP-2026-11-20-M1.36-module-census-4-images.
  - Done when: `docs/firmware/ui-strings.md` with the container layout, counts, the selection path with VAs, and a verdict (replace an existing language / add one / not feasible) with the reason.
  - Stop: one session.
  - Falsifier: the strings are compiled into code sections of many modules rather than one resource.
  - Claims: C-8090–C-8099

- [ ] **M1.53 — move `point_tree_l3`'s STDDLL section walk onto `ce_module` (with a byte-identical capture first)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M1.47 left this as its own falsifier: extend, do not fork)
  - Goal: M1.47's falsifier ("a fifth `_l3.py` that reads ROM sections through `cerom` directly and would have been wrong under the new helper") is `tools/point_tree_l3.py:161` in `Firmware.__init__`: it walks `STDDLL.dll` with its own `rom.o32` loop and calls `nk_decomp.decompress` directly (`IMAGE_SCN_COMPRESSED` at :163), which is the same decode `ce_module.module_sections(..., "STDDLL.dll")` already does (eager, since image start is `0x200200`). M1.47 deferred the move because it had no byte-identical capture of this tool on the factory image; do that capture first, then move the walk and delete the direct `nk_decomp` call (`import nk_decomp` in that method becomes unnecessary).
  - Precheck: `grep -n 'nk_decomp\|IMAGE_SCN_COMPRESSED' tools/point_tree_l3.py` prints the `:161`-`:165` loop and `grep -rln 'IMAGE_SCN_COMPRESSED' tools/*_l3.py | wc -l` prints 3; `python3 tools/point_tree_l3.py --selftest` is green before you start.
  - Scope: `tools/point_tree_l3.py` only (the `Firmware.__init__` STDDLL loop). Do not touch `vcard_l3.py` / `va_class.py` (loader/classifier shapes) or `ce_strfind.py` (a `cecompress` status reader, not this path).
  - Input: `tools/ce_module.py` (`module_sections`, rich 8-tuple, eager at `0x200200`), `tools/point_tree_l3.py` (`Firmware.__init__` :150–175), `tools/nk_decomp.py` (`decompress`, `section_bytes`), EXP-2026-11-22-M1.47-ce-module.
  - Done when: `python3 tools/point_tree_l3.py --selftest` green; `python3 tools/point_tree_l3.py run archive/head256.img --dir <PAIRS> --file POINT010 --json OUT` produces a byte-identical `OUT` before and after (capture both on the same tree, say so in the EXP); `grep -c 'nk_decomp' tools/point_tree_l3.py` drops to 0 in `Firmware.__init__`; `python3 tools/selftest.py` green; the duplicate count `grep -rln 'IMAGE_SCN_COMPRESSED' tools/*_l3.py | wc -l` drops from 3.
  - Stop: if the tool's output differs on the factory image, keep the direct decode and record the differing bytes — do not change the tool's logic.
  - Falsifier: another `_l3.py` that still decodes a section itself after this (`vcard_l3.py:324`, out of scope by shape) — if the helper cannot express its loader-total shape, say so in the EXP rather than special-casing it.
  - Claims: C-8270–C-8279

- [x] **M1.47 — `tools/ce_module.py`: one CE module/section reader for the L3 tools (they each carry their own copy of the ROMHDR → section → bytes path)**
  - Status: done · Owner: task/m1.47-ce-module · Critical: no · Pair: solo
  - Depends: — (tooling; rule 17 allows it because every map L3 task in the window pays the duplication tax — M3.34 and M9.10 both touched the same three helpers)
  - Goal: the same ROM-to-code step is written at least four times, and they drift. `tools/point_walk_l3.py:140 module_sections(data, image_start, module)` returns `(sec, compressed, blob)` only for uncompressed sections; `tools/mapcode_l3.py:136 module_layout(image)` does the same for `AppLaunch.dll` build B with its own `cerom.CERom(image, IMAGE_START)`; `tools/chunk_decoder_l3.py:244 image_init_sections(...)` is the third copy, and the only one that calls `nk_decomp.section_bytes` for compressed sections (H51's rule) — of the 19 `tools/*_l3.py`, 3 import `nk_decomp`; the other L3 tools either silently skip a compressed section or re-implement the decode. When M3.34 added `tools/sh4fpu.py` and M9.10 added a US target, both had to reach into `cerom` by hand again. One owner removes the per-tool choice of "skip compressed" repeated, and makes the H51 rule (a compressed section is decoded by the kernel's own routine, never skipped) atomic.
  - Precheck: `grep -rln 'cerom.CERom(' tools/*_l3.py tools/l3_harness/*.py | wc -l` and `grep -rln 'IMAGE_SCN_COMPRESSED' tools/*_l3.py | wc -l` print the duplicate count on `main` (quote both); `python3 tools/selftest.py --only point_walk_l3 --only mapcode_l3 --only chunk_decoder` is green before you start.
  - Scope: new `tools/ce_module.py` (`--selftest`, synthetic CE fixture, no vendor bytes): `module_sections(image, image_start, module)` → `[(index, va, vsize, psize, compressed, exec, init_len, blob_or_None)]` with the compressed section always decoded through `nk_decomp.section_bytes` (never `None` silently), `text_section(image_start, module)` (the `navi_text` step of `point_walk_l3.py:154`), `find_section(va)` (the `chunk_decoder_l3.py` loop), and `load_image` shared. Then **move** four existing call sites onto it and delete their copies: `point_walk_l3.py` (`load_image`, `module_sections`, `navi_text`), `mapcode_l3.py` (`module_layout`), `chunk_decoder_l3.py` (`image_init_sections`, and its section lookup), `poi_position_l3.py` (the `Navi.exe` section walk at :86). `vcard_l3.py:324` and `va_class.py:48` keep their own for this pass (their shapes differ: a loader total, a classifier) — name them as out of scope in the EXP so a later pass does not re-open it.
  - Input: `tools/cerom.py` (`CERom`, `o32`, `va2file`, `IMAGE_SCN_COMPRESSED`), `tools/nk_decomp.py` (`section_bytes`), `tools/point_walk_l3.py`, `tools/mapcode_l3.py`, `tools/chunk_decoder_l3.py`, `tools/poi_position_l3.py`, AGENTS.md "Compressed `.data` is mostly zeros and import slots".
  - Done when: `python3 tools/ce_module.py --selftest` passes (including "a compressed section is decoded, not `None`" and "a VA in BSS is reported with its init length, not as code"); the four call sites import it and their own copies are gone (`grep -c 'def module_sections\|def module_layout\|def image_init_sections'` is 0 outside `tools/ce_module.py`); `python3 tools/selftest.py` still green **and** the four tools' outputs on `archive/head256.img` are byte-identical before and after (capture both, say so in the EXP); `python3 tools/l3check.py --build-corpus` prints the same `runnable` count before and after.
  - Stop: one session. If moving one call site changes its output on the factory image, stop moving that site, keep the shim, and record the differing bytes — do not "fix" the tool's logic in a refactor.
  - Falsifier: a fifth `_l3.py` that reads ROM sections through `cerom` directly and would have been wrong under the new helper (then the helper's API is too narrow; extend it, do not fork it again).
  - Claims: C-6630–C-6639
  - Result: EXP-2026-11-22-M1.47-ce-module; C-6630–C-6639. ce_module.py owns the CE section walk; point_walk/mapcode/chunk_decoder/poi delegate, seven head256 outputs cmp-identical, selftest 183/0, l3check 3/13 unchanged. point_tree_l3 section walk deferred (falsifier, follow-up)

- [x] **M1.50 — Why the US unit in Poland shows a position in Kentucky (map screen and OpenCARWINGS): GPS receiver, `navdrv` or `Navi.exe`**
  - Status: done · Owner: claude/project-thread-93mdt3 · Critical: no · Pair: solo
  - Depends: —
  - Goal: side track asked by Marek (2026-11-22). His US 2011 unit in Poland shows the vehicle near Somerset, Kentucky (37.4058806, −84.4876444) on the map screen, and OpenCARWINGS reports the same point, updated today. Decide from the firmware which link can hold the position there: the receiver, the `SCI7:` driver, a position filter or default in `Navi.exe`, or the Carwings client; name the measurements on the unit that settle it.
  - Precheck: `python3 tools/ce_strfind.py archive/us256.img --encoding all navdrv` and `--encoding ascii Latitude` print hits.
  - Scope: static, US2011 then EU2011: (1) the GPS path (`SCI7:` user, receiver protocol vocabulary, `GPS`/`Gps` strings, diagnostic screens of `TestMode.exe`); (2) a search of the four heads for the reported coordinate in every encoding the firmware uses (degrees ×10^n, arc-seconds ×100, 1/256 s, `tools/coord.py` units, both byte orders); (3) which module builds the position field of the Carwings request; (4) relation to the area code of M2.7 (`CApi_GetModelArea` consumers). Facts and hypotheses in separate tables.
  - Input: `docs/hardware/head-unit.md`, `docs/firmware/telematics.md`, EXP-2026-11-06-M2.7-us-eu-market, `tools/ce_strfind.py`, `tools/cerom.py`, `tools/sh4xref.py`, `tools/coord.py`.
  - Done when: an EXP that answers (1)–(4) with commands, a list of measurements for Marek on the unit (service screens, NMEA tap) and follow-up tasks added with `board.py add-task`.
  - Stop: one session; the receiver protocol itself is M8.H27, the position store M8.H19, the fix path M8.H29 — reference them, do not do them.
  - Falsifier: the coordinate is found as a constant in a ROM (then it is a factory default, not a last position).
  - Claims: C-8240–C-8249
  - Result: EXP-2026-11-22-M1.50-us-unit-position-kentucky; position to OpenCARWINGS = head unit OBJ_CarPos via Vehicle.exe→DCM_API!SetVehicleData; coordinate not a firmware constant; held last position most likely; follow-ups M1.51, M1.52

- [ ] **M1.51 — `Navi.exe`: does it accept a GPS fix far from the current car position?**
  - Status: open · Owner: — · Critical: yes · Pair: solo
  - Depends: —
  - Goal: side track for Marek's car (EXP-2026-11-22-M1.50 update): the receiver has a valid fix in Wrocław but a 2007 date (1024-week rollover), while the navigation car position stays in Kentucky. Find the check between OBJ_GpsInfo and OBJ_CarPos that drops the fix: a date comparison (H2a), a distance/jump limit (H2b) or map matching (H2c).
  - Precheck: `python3 tools/sh4xref.py archive/us256.img OBJDLL.dll --image-start 0x200200 --to 0x0346dd7c` names the user of the `LAST` string.
  - Scope: static, US2011: the writers of `OBJ_GpsInfo` and `OBJ_CarPos` in `Navi.exe`/`OBJDLL.dll`, the comparison between fix and dead-reckoned position (distance threshold, count of agreeing fixes, off-map check), what `navdrv!SetFilterConfig` sets.
  - Input: EXP-2026-11-22-M1.50, `tools/sh4xref.py`, `tools/callgraph.py`, M8.H29 if merged.
  - Done when: an EXP naming the function that turns a fix into the car position and its accept rule with VA (or "no distance rule found" with the searched callers); claims.
  - Stop: one session; if the rule sits in another process, name the message and stop.
  - Falsifier: the car position is written from the fix unconditionally.
  - Claims: C-8250–C-8254

- [ ] **M1.52 — TestMode GPS initialisation: how to seed the receiver with a Polish position and the date**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: —
  - Goal: side track for Marek's car (EXP-2026-11-22-M1.50, hypotheses H1/H1a): `TestMode.exe` writes a date and lat/lon to the GPS receiver (`CTestModeGPSInit::WriteGpsData`, US `fn 0x0003aa80`). Find the screen that calls it, the text format the technician enters, and what the `B0_A3`, `B0_A0`, `B3`, `B4` commands do, so Marek can try it on the unit.
  - Precheck: `python3 tools/sh4xref.py archive/us256.img TestMode.exe --image-start 0x5200200 --to 0x198f0` prints `fn 0x0003aa80`.
  - Scope: static, US2011 then EU2011: callers of `0x0003aa80` up to a screen/button, the source of the text fields at object +0x8c/+0x94, the date frame of `fn 0x00043da8`, the four `GpsDataSet*` frames (`fn 0x0004443c`, `0x00044494`, `0x000444ec`, `0x0004453c`), how TestMode is entered (EXP-2026-11-05-M2.10-testmode).
  - Input: EXP-2026-11-22-M1.50, `tools/sh4dis.py`, `tools/sh4xref.py`, `docs/hardware/head-unit.md`.
  - Done when: a page section (in `docs/hardware/head-unit.md` or a new `docs/firmware/gps.md`) with the steps on the unit and the frame table with VAs; EXP + claims; a hand-encoded example frame for 52.23 N 21.01 E.
  - Stop: one session; nothing is sent to a real unit by the agent.
  - Falsifier: no caller of `0x0003aa80` is reachable from a screen (dead code).
  - Claims: C-8255–C-8259

- [ ] **H120 — Three checks that say PASS when nothing was checked (found by running the tools on a clean host)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (serves M5.61 and M5.35: their gates run the card verifier chain on hosts we do not control; rule 17)
  - Goal: QA cycle 18 ran the test tools in a fresh cloud container and three of them reported a result they had not measured. (1) `python3 tools/verify.py --image IMG --strict` printed `L2: SKIP (7z not found; L2 skipped)`, then `RESULT: PASS`, exit 0 — a card "passes" with L2 never run. (2) No gate compiles the tools: `tools/ce_rom_parse.py` was a `SyntaxError` on `main` at `13cb0cf` (fixed in the SE pass) and `selftest.py` did not notice, because it only discovers tools that have `--selftest`. (3) `python3 tools/l4_status.py` prints `F4 BLOCKED (M8.A3, M8.A6, M9.16)`; the list is a constant and M8.A3 and M8.A6 are done.
  - Precheck: on a host where `command -v 7z` prints nothing, `python3 tools/verify.py --image IMG --strict; echo $?` prints `L2: SKIP (7z not found; L2 skipped)`, `RESULT: PASS` and `0` (the defect; seen 2026-11-20 on the EU2011 image); `python3 tools/l4_status.py | grep 'F4 BLOCKED'` names M8.A3.
  - Scope: `tools/verify.py` (a skipped level is never `PASS`: `RESULT: INCOMPLETE (L2 NOT RUN: <reason>)`, exit 3 with `--strict`, the level named in the result line without it); `tools/selftest.py` (first step: byte-compile every `tools/**/*.py` and `.github/scripts/*.py`, a file that does not compile is a FAIL row); `tools/l4_status.py` (`blocked_by` stays the declared list, the printed list drops IDs whose block is `done` in `TODO.md`, or whose block is archived). No workflow change: CI already runs `selftest.py`.
  - Input: `tools/verify.py`, `tools/selftest.py`, `tools/l4_status.py` (`--selftest` asserts the literal F4 string today, update it), `docs/research/test-system.md` §4 (status classes).
  - Done when: with no extractor on `PATH`, `verify.py --image IMG --strict` exits 3 and prints `INCOMPLETE`; `verify.py --selftest` covers it with a faked missing extractor; `python3 tools/selftest.py` exits 1 on a temp tree that holds one file with a syntax error and 0 on `main`; `python3 tools/l4_status.py` prints `F4 BLOCKED (M9.16)` today and its selftest proves a `done` blocker is dropped and an unknown ID is kept; `python3 tools/gate.py` green.
  - Stop: if compiling every tool adds more than 10 s to `selftest.py`, compile only files changed against `origin/main` in CI and all files locally, and record the two timings.
  - Falsifier: a second tool that prints `PASS` after a `SKIP` line in the same run (then the status class belongs in one shared helper, say so in the EXP).
  - Claims: C-6340–C-6349

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

- [x] **H125 — Prose freshness is unchecked: TODO task text goes stale while the EXP/claim already says otherwise, and no tool flags it**
  - Status: done · Owner: task/h125-unblock-done-target · Critical: no · Pair: required
  - Depends: — (rule 17: this is the tool half of a record defect the SE pass found; no map task depends on it, so it also needs a `Pair:` and one bounded session)
  - Goal: three tasks on the board say the opposite of what their result proves, and every checker stays green because all of them judge structure, never prose. (1) M3.29 is `blocked` with `Unblock: M9.53`, and M9.53 is `done` since 2026-11-20 16:54Z (`EXP-2026-11-20-M9.53-record-block-read`), so rule 15's re-open never fired — a one-cycle-old dead-end labelled that way (the task's own Result says the Stop rule was met, so re-opening may not be the fix). (2) M3.13, M3.14 and M3.16 are `blocked` on M3.30, whose status line is `open · Owner: —` and whose own `Depends` says it "cannot be taken until M3.29 merges done" — an open door onto a locked room. (3) M4.23's `Unblock` names M4.25 and M4.26, which were archived `[x]` on 2026-11-09 (`docs/research/todo-history-2026-11-09.md`, both `done`), so the token it waits on can never merge again. `todo_check.py` reports the archived case only as WARN (`TODO.md:5146 M9.56: Depends references blocked task ID 'M4.40'` is the census of the class), and nothing reports an `Unblock` that names a `done` task.
  - Precheck: `python3 tools/board.py show M3.29 | grep -m1 Status:` prints `blocked`; `python3 tools/board.py show M9.53 | grep -m1 Status:` prints `done`; `python3 tools/todo_check.py | grep -c 'WARN.*archived task ID'` is non-zero on `main` at this commit.
  - Scope: `tools/todo_check.py` gains one rule, exit 1 (not WARN) with `--strict`: for every `blocked` task, an ID in its `Unblock:` that resolves `done`, or an archived task, is an ERROR naming the task and the ID — this is the rule-15 hole that left M3.29 and M4.23; for every `open` task, an `Unblock:`/`Depends` line that says *cannot be taken* and names an ID that is also `open` is a WARN (a chain of open doors; the M3.30 text is the fixture). A `--fix-list` prints `task / field / id / target-status`. The audit itself (M3.29, M3.30, M4.23) is the parallel task M3.36; this task ships only the checker and does not edit those task blocks.
  - Input: `tools/todo_check.py` (`TASK_RE`, `FIELD_RE`, the `WARN ... archived task ID` branch M9.2/M9.5/M9.14 already hit), `tools/board.py` (`show`), `docs/research/todo-history-2026-11-09.md` (M4.25/M4.26), the M3.29/M3.30/M4.23/M9.53/M4.25/M4.26 blocks on `main`.
  - Done when: python3 tools/todo_check.py --strict exits 1 on main at this commit and names M3.29 (Unblock M9.53 done) and M4.23 (Unblock M4.25 archived); the selftest covers three cases — an Unblock that names a done task (ERROR), one that names an archived task (ERROR), and one that names an open task (no error) — and a fixture board where no blocked task has a done/archived Unblock exits 0; tools/gate.py stays green on the current board minus the two known offenders (measured by running it on a temp copy with those two Unblock lines blanked). This task ships the checker only; fixing the two blocks is M3.36 and is not required here.
  - Stop: one session. If `todo_check` cannot tell an archived ID from a ghost without the history files, ship the `done` case only, and file the archive case as its own task — do not guess.
  - Falsifier: a `blocked` task on `main` whose `Unblock` names a `done` task that the new rule does not print. Then the rule reads the wrong field, and the pair fixes the field, not the test.
  - Claims: C-6590–C-6599
  - Result: EXP-2026-11-21-H125-unblock-done-target (C-6590–C-6593). `todo_check.py --strict` exits 1 and names M3.29 (Unblock M9.53 done) and M4.23 (Unblock M4.25/M4.26 archived); the class census is 5 blocked tasks / 9 refs (M3.16, M3.18, M4.51 are the same hole) = 8 prior + 9 new strict errors; default `todo_check` exit 0 and `gate.py` 4 pass / 0 fail / 0 skip (fn_audit PASS); selftest 43 checks covers done/archived ERROR + open no-error. Board repair is M3.36.

- [x] **H126 — PR checks go stale: a push to a PR head after its last run leaves zero check-runs, and nothing re-runs or refuses the merge**
  - Status: done · Owner: task/h126-stale-pr-checks · Critical: yes · Pair: required
  - Depends: — (H98 branch protection is the preferred fix and stays its own block; this is the mechanical half that also catches the stale case)
  - Goal: QA cycle 20 found M8.C1 #394 in the open-PR set with a head commit `99d0b54` (authored on `main` as `b90f9d47`) that has **0** check-runs: `gh api repos/neutrinus/OSM2Leaf/commits/99d0b54b88290066a5d587d5a0a9e3ecb7b946dd/check-runs -q .total_count` prints `0`, while the previous head `6b55ccd0` has 6 and both passed on-topic. The board and the reviewers therefore see "no checks reported" and a green-looking PR whose tip was never tested — the same class as H90 (a defect no local gate could see) but on `pull_request` runs instead of `main`. `gh pr checks 394` exits 1 with `no checks reported on the 'task/m8.c1-hpb-dmac' branch`. The `pull_request` trigger does fire on a pushed head, so the failure is either a skipped re-run, a force-push that GitHub coalesced, or a head that was rewritten during a rebase; the check must say which.
  - Precheck: `gh pr checks 394` prints `no checks reported` and exits 1; `gh run list --workflow "CI quality gate" --branch task/m8.c1-hpb-dmac --limit 6 --json headSha -q '.[].headSha' | sort -u` prints `6b55ccd…`, `19748d2…`, `738817d…` — never `99d0b54`; `gh api …/commits/99d0b54…/check-runs -q .total_count` prints `0`.
  - Scope: `.github/workflows/main-watch.yml` and `.github/scripts/main_watch.py` only (no gate-semantics change; `tools/gate.py` untouched). Add a PR-head sweep beside the `main` sweep: for every open non-draft PR, the head SHA must have >=1 completed gate check-run whose conclusion is not `cancelled`; otherwise the watchdog fails and names the PR, the head SHA and the last-tested SHA (or `none`). Run it from the existing hourly `schedule` and `workflow_dispatch` (it needs `pull-requests: read` and `actions: read`), never as a per-PR blocking status (no branch protection yet, H98). Exclusion: do not re-push or re-run checks for the author; only report and fail the watchdog.
  - Input: `.github/workflows/ci.yml` (the `pull_request` trigger), `.github/scripts/main_watch.py` (`classify`, `is_red`, `--replay`, the `[H117]` issue flow), `.github/workflows/main-watch.yml`, M8.C1 #394 as the fixture, H117's EXP for the issue-body shape.
  - Hints: use `gh api …/commits/<sha>/check-runs` rather than `gh pr checks`, because the latter exits 1 with prose that a script cannot classify. A PR whose head equals the last run's head but the run is `queued`/`in_progress` is not stale — wait for it. Keep the `main` verdict line byte-identical so the H117 issue marker still matches; add a second issue marker for the PR sweep (`<!-- h126-stale-pr -->`).
  - Done when: `python3 .github/scripts/main_watch.py --selftest` classifies a fixed PR list containing one stale head (no check-run) and one tested head, and the stale one fails; a `--replay` against a saved PR-head document reproduces the #394 verdict (`stale`, head `99d0b54`, last tested `6b55ccd0`); with the current live list the command names #394 and nothing else; the workflow's `schedule`/`workflow_dispatch` path runs it; `tools/gate.py` stays 4 pass / 0 fail / 0 skip.
  - Stop: if GitHub reports the check-run list for `99d0b54` as `pending` (not `none`) for more than one sweep, record that a re-push is required and close the task as `blocked` naming the PR — do not treat a `pending` that never completes as a pass.
  - Falsifier: an open non-draft PR whose head has 0 completed gate check-runs and the watchdog still exits 0.
  - Claims: C-6670–C-6679
  - Result: EXP-2026-11-22-H126-stale-pr-heads (C-6670): .github/scripts/main_watch.py --prs sweeps every open non-draft PR head via gh api check-runs; 0 completed non-cancelled gate runs = stale (pending waits, cancelled-only stale, non-gate run ignored, draft out of scope); opens/updates [H126] fix: issue and exits 1, never re-runs for the author. Fixture #394: 99d0b54 has 0 check-runs, 6b55ccd0 has 6; --replay-pr prints stale #394 head 99d0b54b last tested 6b55ccd0 rc=1; selftest 34 checks; tools/gate.py 0 fail. Workflow runs the sweep from the hourly schedule/workflow_dispatch with pull-requests: read.

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

- [x] **H129 — `board.py claim-set` writes `Supersedes:` to the evidence cell, and its selftest does not check the target cell**
  - Status: done · Owner: task/h129-claim-set-supersedes · Critical: no · Pair: required
  - Step: tooling
  - Depends: — (found by the M1.44 round-3 reviewer after #433 merged; it is a tool bug, not a record defect)
  - Goal: `python3 tools/board.py claim-set C-XXXX Supersedes C-YYYY` must put `Supersedes: C-YYYY` in the claim **body** (cell 2) when the body has no such key, matching every other ledger row's body form (C-6460's body itself says "Supersedes: C-6460"); it must not silently append `; Supersedes: …` to the evidence cell (cell 5). Evidence: M1.44 #433 merged as `47400e9b`; C-6750's `Supersedes` landed in the evidence tail (`| … status | … evidence …; Supersedes C-6460, whose scope… |`) and `claim-set` is a no-op on a second call.
  - Input: `tools/board.py` `_claim_row`/`op_claim_set` (the `for ci in (2, 5)` order and the `else` fallback), the `claim-set` selftest's "claim-set keeps IDs" assertion, and the C-6750/C-6460 rows as the live specimen.
  - Done when: `python3 tools/board.py claim-set C-6750 Supersedes C-6460` on the current ledger leaves one `C-6750` row with `Supersedes: C-6460` inside cell 2 and the evidence cell unchanged (print the row before/after, split on unescaped `|`); `python3 tools/board.py --selftest` has a case that fails if the field lands in cell 5 instead of cell 2; `python3 tools/claims_check.py --strict --count-check` OK; `python3 tools/gate.py` = 5 pass / 0 fail / 0 skip (`board_check` PASS, `fn_audit` not SKIP).
  - Stop: if a real ledger convention turns out to be "Supersedes lives in evidence", record that with a counted corpus and close this task with a negative result rather than moving 199 rows.
  - Claims: C-6760–C-6769
  - Result: EXP-2026-11-22-H129-board-claim-set-supersedes-cell; claim-set inserts missing keys into body cell 2, selftest pins cell placement; C-6750 normalized via claim-set.

- [x] **H130 — `board.py claim-body`/`claim-set` split a row on a raw `|` inside the claim text, corrupting the row and injecting the tail into the next one**
  - Status: done · Owner: task/h130-claim-pipe · Critical: no · Pair: solo
  - Step: tooling
  - Depends: — (found by the M4.61 driver 2026-11-22 while widening C-6564; H129 fixed which cell a key lands in, not the cell splitting)
  - Goal: `_claim_row` splits a row with `re.split(r"(?<!\\|)\\|", line)` and `op_claim_body` / `op_claim_set` re-join with `"|".join(parts)`. A claim body that contains a raw `|` (e.g. the POINT pair written as `(0x800|flon, flat)`, a natural way to write a bitwise OR) is therefore split into extra cells; `claim-body` then writes the new text into cell 2 and keeps the old tail, so the row ends with `... |flon, flat)` pair at ... | VERIFIED | ...` and the next row's leading cells are lost or duplicated. The tool reports success (`board: C-6564 body replaced`) and `claims_check` still exits 0, so the corruption is silent. This is the same class as H129 (a write that passes checks but is wrong) and needs an escaped-pipe convention plus a row-shape guard.
  - Precheck: `python3 tools/board.py --claims /tmp/opencode/h130-claims.md claim-body C-6564 "a (0x800|flon, flat) pair"` on a copy of the ledger prints `body replaced` and leaves a row with more than 7 pipe-split cells; `python3 tools/claims_check.py --claims /tmp/opencode/h130-claims.md` still exits 0.
  - Scope: `tools/board.py` `_claim_row`, `op_claim_body`, `op_claim_set`, `op_claim_row` and their selftests. No ledger row is rewritten by hand; the fix must refuse or escape, not guess.
  - Input: `tools/board.py` (`_claim_row`, `op_claim_body`, `op_claim_set`, `op_claim_row`), the H129 block and `EXP-2026-11-22-H129-board-claim-set-supersedes-cell`, the M4.61 round where C-6564 was corrupted by `claim-body` and repaired with `claim-row`.
  - Done when: a claim text containing `|` is either escaped (`\\|`) on write and unescaped on read, or refused with a clear error, and a row with more than the 7 expected cells (or fewer) is refused before any write; `python3 tools/board.py --selftest` has a case that writes a body containing `|` and asserts the row still has exactly 7 pipe-split cells and the neighbouring rows are unchanged; `python3 tools/claims_check.py --strict --count-check` OK; `python3 tools/gate.py` = 5 pass / 0 fail / 0 skip.
  - Stop: if the ledger convention is "claim text never contains a raw pipe", make the tools refuse it and record that rule in `AGENTS.md` instead of adding escaping.
  - Falsifier: a `|`-containing body that round-trips through `claim-body` and leaves the row at 7 cells and the next row intact — then the split is not the defect and this task is closed negative.
  - Claims: C-8260–C-8269
  - Pair: required
  - Result: EXP-2026-11-22-H130-board-claim-raw-pipe; claim-body/claim-set escape raw pipes; exact-7 cell guard; 105/105 board selftests; gate 5 pass/0 fail/0 skip


## M2 — Map code, activation, updater

- [x] **M2.4 — Predict accept/reject for the 89 `HDD_INFO` variants**
  - Status: done · Owner: task/m2.4-hdd-info-predict · Critical: yes
  - Re-opened (rule 15, M9.6 merged 2026-11-19): `runner.py run applaunch_mapcode_compare --image IMG256 --input VARIANT --unit-from FACTORY` gives the firmware check-1 verdict per variant (EXP-2026-11-19-M9.6-mapcode-compare); the blocker below is kept as a note.
  - Depends: — (**M9.6 merged** `ff8720d`, M2.15 and M2.3 done); the corpus and
    the comparator are both on `main` now
  - Note (sixth pass): the old blocker ("firmware verdicts need the L3 target,
    unavailable offline") was **wrong** — M9.6 runs the comparator offline with
    a stubbed `KernelIoControl(0x0101302C)`, and M2.15 supplied the exact card
    bytes plus the `+96`/`+112`/`+114` unit fields. Only M9.6 is missing.
    The offline model-M0 gives 66 ACCEPT / 23 DIFFERENT
    (EXP-2026-11-06-M2.4-hddinfo-variants).
  - Blocker (resolved by M9.6, kept as note): M9.6 is merged (`ff8720d`) and M9.20 module-entry plumbing is on
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
  - Earlier result (2026-11-08, blocked): EXP-2026-11-08-M2.4-hddinfo-variants-blocked (negative:
    firmware verdicts unavailable; C-2086 retains M2.15-model offline
    reclassification of all 89).
  - Claims: C-5290–C-5295 (was C-750–C-759; fresh block for this run; C-5296–C-5299 go to M2.19)
  - Result: done — EXP-2026-11-19-M2.4-hddinfo-fw-verdicts. `tools/hddinfo_fw_matrix.py run` puts all 89 variants through EU2011 build B `fn 0x03bd2ad8` (check 1): firmware 69 ACCEPT / 20 REJECT, agrees with `hddinfo.py classify` check 1 on 89/89 (factory ACCEPT, no-file REJECT controls ok); M0's 66/23 is refuted. Edge probes are consistent with a byte-exact compare of line-1 bytes 0..10 (BOM, lower case, leading space fail; 10 probes + 14 line-1 edits), and LF-only / line-1-only files pass check 1 although `hddinfo.py` refuses them (C-5290–C-5295). Check 2 (`0x51`) is M2.19.

- [x] **M2.19 — Check 2 (MapDBVer, `0x51`) and the router on the `HDD_INFO` variants in L3**
  - Status: done · Owner: task/m2.19-check2-router-l3 · Critical: no
  - Depends: M2.4 (done), M9.6 (done)
  - Goal: run AppLaunch `fn 0x03bd2ce4` (MapDBVer range, EU2011 build B) and the router `fn 0x03bd2ecc` on the 89 variants, so each has a full launcher verdict, not only check 1.
  - Precheck: `python3 tools/nk_decomp.py pdata --image-start 0x3e00200 --module AppLaunch.dll archive/head256.img 0x03bd2ce4 0x03bd2ecc` gives `START` for both; `python3 tools/sh4dis.py --image-start 0x3e00200 --va 0x03bd2ce4 --count 120 archive/head256.img AppLaunch.dll` shows its imports are a subset of the 8 `mapcode_l3` stubs (else name the missing one).
  - Scope: EU2011 build B only; unit bounds `+112/+114` are declared inputs (bracketing the factory MapDBVer `0x010`), not measurements; the 12 MapDBVer-changing variants (C-3034) are the ones that can move.
  - Input: `tools/mapcode_l3.py`, `tools/hddinfo_fw_matrix.py`, `hddinfo.py` (`extract_mapdbver`), EXP-2026-11-19-M2.4-hddinfo-fw-verdicts.
  - Done when: each of the 89 variants has a check-2 firmware verdict under a stated bounds pair, compared with `hddinfo.py classify --mapdbver-min/--mapdbver-max`, plus a run of the router that returns `0x50`/`0x51`/pass.
  - Stop: if check 2 needs the parse cache filled by a prior check-1 call and the harness cannot chain the two calls, or calls an unmodelled import, set `blocked` with the PC.
  - Claims: C-5296–C-5299
  - Result: done — EXP-2026-11-20-M2.19-check2-router-l3. `tools/hddinfo_check2_matrix.py` runs check 2 `fn 0x03bd2ce4` and the router `fn 0x03bd2ecc(0)` (EU2011 build B) on the 89 variants: check 2 = `hddinfo.py classify` 89/89 under `0x010:0x010` (77/12) and `0x001:0x0ff` (81/8), logged MapDBVer = model 20/20; router codes = model failures 89/89 with a returning dispatcher (2 rows `0x50`+`0x51`) and first-code-only with a halting one. `validation.md`'s "does not skip check 2" corrected: on a production unit check 2 runs only after check 1 passes (C-5296–C-5299).

- [ ] **M4.23 — Tile section-2 regulation/connectivity reader (kinds `0x2046`/`0x3e4`)**
  - Status: blocked · Owner: claude/m4.23-restriction-encoding · Critical: no
  - Step: P2
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
  - Step: P2
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

- [ ] **M2.21 — Acceptance gates in the emulator: a wrong `HDD_INFO.TXT` and a wrong map code at L4**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: reader
  - Depends: M8.H13
  - Goal: The card-acceptance rules (M2.1–M2.19) were read statically and at L3; the car test S0–S3 is their only full check and it is expensive. `-M ze0` now runs the launcher. Reproduce the gates there: each known reject condition should stop at the predicted place.
  - Precheck: `python3 tools/l4check.py --card EUCARD --json` exits 0 on the factory card.
  - Scope: EU2011: three cards built in place with `tools/imgpatch.py` — `HDD_INFO.TXT` label changed, map code changed, the `0x06000000` copy changed; also `verinf` of the unit changed with the card intact. Compare stage and log with EXP-2026-11-05-M2.9-error-catalogue.
  - Input: `tools/l4check.py`, `tools/imgpatch.py`, `tools/hddinfo.py`, EXP-2026-11-05-M2.9-error-catalogue, EXP-2026-11-19-M2.4-hddinfo-fw-verdicts.
  - Done when: an EXP table mutation → predicted verdict (from M2.4/M2.9) → L4 verdict → agree?; every disagreement is a claim correction in `docs/research/claims.md` through `board.py`.
  - Stop: one session.
  - Falsifier: all mutated cards pass like the factory card (then the launcher path in the emulator skips the check: find which precondition is missing).
  - Claims: C-8030–C-8039

- [ ] **M2.22 — Does a fully rebuilt card boot? `mkcard` output against in-place patching, at L4**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: reader
  - Depends: M8.H13
  - Goal: The fourth PM review ruled that test cards must be patched in place because a rebuilt card loses the volume label and has a new FAT layout. That rule costs every card-building task. Test it in the emulator: which of the differences actually matters to the firmware.
  - Precheck: `python3 tools/mkcard.py --help` works and `python3 tools/l4check.py --selftest` passes.
  - Scope: EU2011: (a) factory card, (b) `mkcard` rebuild of the unchanged tree, (c) rebuild with the label restored, (d) in-place no-op; compare L4 verdicts and the first differing log line.
  - Input: `tools/mkcard.py`, `tools/imgpatch.py`, `tools/l4check.py`, `tools/cardcheck.py`, `docs/format/sd-card-layout.md`.
  - Done when: an EXP table card → L1 → L4 stage → verdict, and one sentence that keeps, narrows or lifts the in-place rule in `docs/research/card-test-plan.md`.
  - Stop: one session.
  - Falsifier: (b) and (a) behave the same in the emulator while the rule says (b) fails on the unit — then the emulator lacks the check, and the EXP names the check (label read, cluster layout) to model.
  - Claims: C-8040–C-8049

- [ ] **M2.23 — The SD lock in the emulator: locked, unlocked and wrong-password cards**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: M8.C1b (done)
  - Goal: On the unit the card is password-locked (CMD42) with a unit-specific password; the emulator's SD model accepts the password 'on first use'. Make the model strict enough to test the firmware's behaviour with an unlocked card and with a card locked to another unit — the question behind 'can a self-made card work without the lock'.
  - Precheck: `grep -n -i 'lock\|CMD42\|first use' tools/qemu-ze0/patches/ze0-0008-hw-sh4-ze0-sd-host.patch tools/qemu-ze0/patches/ze0-0009-hw-sh4-ze0-hpb-dmac.patch` shows the current behaviour.
  - Scope: machine/`sd-card` options for three card states (no password, right password, other password) without storing any real password in the repo (use a test value and the unit record of `ze0-0010`); boot each; log the CMD42 exchange and the launcher verdict.
  - Input: `ze0-0008`, `ze0-0010`, EXP-2026-11-06-M2.13-sd-password, EXP-2026-11-06-M2.13b-sdhc-cmd42, `tools/ze0_sdhost.py`.
  - Done when: an EXP table card state → CMD42 sequence → launcher verdict; a statement whether the firmware refuses a never-locked card, with the VA of the decision.
  - Stop: one session.
  - Falsifier: the three states give the same boot (then the lock is not checked on this path).
  - Claims: C-8050–C-8059

- [ ] **M2.24 — The error screens, seen: reproduce the catalogue of card errors at L4 with screenshots**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: M2.21, M8.C1f
  - Goal: M2.9 listed the error messages the firmware can show for a bad card. With a working screen, show each one in the emulator and tie it to its trigger — the reference for anyone who later sees one in the car.
  - Precheck: `tools/ze0_screenshot.py grab` shows a UI screen and M2.21's cards exist.
  - Scope: one screenshot per reachable error (kept in `archive/`, hash and wording in the record), trigger card, log line.
  - Input: EXP-2026-11-05-M2.9-error-catalogue, M2.21's EXP, `tools/ze0_screenshot.py`.
  - Done when: `docs/format/validation.md` gains a table error text → trigger → log line → screenshot hash for at least three errors.
  - Stop: one session.
  - Falsifier: an error in the catalogue is unreachable by any card mutation tried.
  - Claims: C-8060–C-8069

- [x] **M2.25 — Where do the 4 unit bytes of the SD password come from (VIN, serial, or stored)?**
  - Status: done · Owner: claude/project-thread-i59j9z · Critical: no · Pair: solo
  - Depends: — (M6.18 dump: PROD, NAND, SRAM, VFlash of the owner's unit)
  - Goal: The owner asks whether the SD card PIN can be worked out from the VIN alone. Say where the unit takes the 4 bytes from and what a person needs to learn them.
  - Scope: search the four dumps for the PIN, serial and VIN; disassemble the flash loader routine that uses the tail literal. No PIN bytes, no serial, no dump in the repo.
  - Done when: an EXP names the storage offset, the routine (VA) that reads it, and answers "VIN alone: yes/no".
  - Stop: one session.
  - Claims: C-8300–C-8309
  - Result: EXP-2026-11-22-M2.25-sd-pin-source (C-8300–C-8305). VIN alone: no. The 16-byte password is stored verbatim at PROD +0x100 (flash 0xA100; the 4 unit bytes again at +0x60); the flash loader routine VA 0x8b0232ac copies it and falls back to 99 99 99 99 + tail when PROD is not valid. No VIN in NAND/SRAM/VFlash, no code computes the bytes. Factory rule (random or from serial) unknown with one unit.

- [x] **M2.26 — Does Navi.exe (or any menu field) derive the SD PIN from the serial?**
  - Status: done · Owner: claude/project-thread-i59j9z · Critical: no · Pair: solo
  - Depends: M2.25 (PIN stored in PROD)
  - Goal: Answer whether a reseller could compute the PIN from a field the user reads off the menus; check the navigation application for a serial->PIN (or Confirmation-code) routine.
  - Scope: US256 image A Navi.exe (imports, strings, decompressed data); offline test of the menu numbers vs the PIN. No PIN/serial/VIN/dump in the repo.
  - Done when: an EXP states whether Navi.exe touches the PIN and whether any menu number maps to it.
  - Stop: one session; do not chase the Confirmation-code routine beyond locating its owner.
  - Claims: C-8330-C-8339
  - Result: EXP-2026-11-22-M2.26-navi-no-pin-formula (C-8330-C-8334). No menu number equals or maps to the PIN; Navi.exe (834 imports) has no SD-lock/CMD42/password code and never touches the PIN. Confirmation code is a separate 16-bit activation value (routine outside Navi.exe). A reseller never needs the PIN - the unit locks its own card. No serial->PIN formula found.

## M3 — Reader contract

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

- [x] **M3.2b — Find the `.cmp` chunk reader by walking up from `inflate`**
  - Status: done · Owner: — · Critical: yes
  - Note (H51, 2026-11-11): **re-opened: the search target was wrong, not the method.** `0x0041c7e8` is the seventh instruction of `fn 0x0041c7dc` (pdata: prologue 30 B, length `0xe8`); nothing references a mid-prologue address. `python3 tools/sh4xref.py IMG256 Navi.exe --image-start 0x200200 --to 0x0041c7dc` → pool `0x0041caac`, caller **`fn 0x0041c990`** (`jsr` at `0x0041ca5a`), whose caller is **`fn 0x0041c044`** (`jsr` at `0x0041c096`). Next: disassemble `0x0041c990` (length `0x120`) — it is the loop over the chunk table and should answer M3.2 (chunk size source, seek vs scan); walk up from `0x0041c044` to the function that opens the `.cmp`/`.ind` pair (M3.23 `callers`). Then fix `FN_CHUNK` in `tools/chunk_decoder_l3.py` to the true entry (H52) and re-run M9.11. No sec1 decode is needed for any of this.
  - Depends: — (**not** M1.2f for the code: no executable section of build A is
    compressed, C-2128)
  - Blocker: no literal-pool/direct/32-bit reference to `0x0041c7e8` in any
    uncompressed section of build A (282 sections, 149 modules) or B/C; the
    likely indirect-call pointer lives in `Navi.exe` sec1 (`.data`,
    `0xc8002040`, compressed) which `cerom decompress` cannot decode
    (`UNSUPPORTED`, LZX/LZSS). Zlib is in uncompressed sec0 (C-2060), so the
    Done-when escape is false. A firmware `.cmp`-open L3 probe for the caller
    PC needs file-stub/import binding (M9.24 context). M3.2a/b unanswered.
  - Note (H50, EXP-2026-11-10-H50-va-class-prechecks): no concrete sec1 blocker VA cited in this task; next owner must provide a concrete VA for va_class classification before claiming a compressed-sec1/M1.2f blocker (leave status unchanged).
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
  - Result: EXP-2026-11-19-M3.2b-cmp-chunk-reader-walk-up.md (done, pass 3, C-5100–C-5109). EU2011: `0x542148` <- `0x41c7dc` <- `0x41c990` <- `0x41c044` <- `0x41b954` <- `0x41855c` <- `0x418634` <- `0x419df8` (message handler); the `chunk_offset[]` loop is `0x41c5f0`; open `0x417fe0` -> `0x41b780` -> `0x41be30` (`CMP.LST` match `0x41c2e0`, which is read at mount, C-5103) -> `0x41c524` (`fopen(path+".CMP")`). M3.2: `chunk_size` compared `== 0x10000` (`0x41c92a`, `0x41c696`), seek by offset, no scan; answers in `cmp-ind.md`. New `tools/cmp_reader_contract.py`: factory EU 194/194 pass the firmware's rules. Corrects C-1866, C-4446–C-4448. readers 6 -> 7/30 (row 6 located).
  - Earlier result: EXP-2026-11-08-M3.2b-cmp-chunk-reader-inflate-2.md (blocked, pass 2).
    Inflate/engine VAs confirmed (C-2061–C-2063); 0 refs to `0x41c7e8` in all
    uncompressed sections of A/B/C (C-2064 strengthened); sec1 `.data`
    `UNSUPPORTED` by `cerom decompress` (C-2067); `.ind` consumer/indirect
    caller unresolved, M3.2a/b open (C-2066 refined). Pass 1:
    EXP-2026-11-06-M3.2b-cmp-chunk-reader-inflate.md.
  - Claims: C-5100–C-5109 (was C-2060–C-2069; fresh block for this run)

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

- [x] **M3.11b — Where the `POINT` page becomes native u16**
  - Status: done · Owner: task/m3.11b-point-byteorder · Critical: yes
  - Result: EXP-2026-11-20-M3.11b-point-byteorder-2 (C-5810–C-5816; done).
    Done-when met on real bytes with `tools/swap_witness_l3.py run` (which boots
    the EU factory card through `vcard_l3.py`): the firmware's own loop
    `0x00417f1c` inside the completion `fn 0x00417eac` swaps the factory
    `REFER001/POINT010.DAT` first page when request word +20 = 0 (2,048
    iterations for `0x1000`, 512 for `0x400`); pre-loop bytes = unswapped host
    decode `10dceb1a…9ebf`, post-loop and returned bytes =
    `point_walk_l3.swap16(host)` `a6c6fec3…260c` (`RESULT: PASS`, exit 0);
    +20 = 1 never enters the loop and returns the stored bytes. Client is
    `0x003f6c88` (C-4672), `.cmp` chain decode-only (C-3604). C-2547–C-2549
    unchanged.
  - Note (M9.44, 2026-11-19): **the swap is found** (C-4641): the map-file layer's completion routine `0x00417eac` swaps every byte pair of the read buffer when request word +20 is 0 (1 = as stored). `python3 tools/vcard_l3.py read IMG256 --card-image CARD REFER001/POINT010.DAT --length 0x1000 --swap` shows it on the real file. What remains for this task: name the client that queues the `POINT` read with word +20 = 0 (callers of `0x0041841c`), then close.
  - Note (M3.28, 2026-11-19): **the client is named** (C-4672): `0x003f6c88` is the only caller of the read API; it `memset`s the request and never stores to +20, so every client read (not only `POINT`) comes back byte-swapped. Both halves of this task's question are answered; close it with a pointer to C-4641 and C-4672.
  - Note (M9.38, 2026-11-19): the reader list is in. The walker reads the page with one 2-byte native load (`mov.w`, EU `0x003f519c` / US `0x0041db4c`) via the real dispatcher (`0x003f5cdc` / `0x0041e63c`), entry `0x003f5194` / `0x0041db44`. **The chunk-engine caller `fn 0x0041c044` is decode-only**: watching its destination `0x50000000` on EU `POINT010` shows writes only from the stubbed `memcpy` and **no guest read**; so the swap is not on the `.cmp` path. Watched VA per run: EU `0x50000000` (chain), page `0x20000000` (walk); C-3602–C-3605, EXP-2026-11-19-M9.38-read-watch.
  - Note (H51, 2026-11-11): answer it dynamically with **M9.38** (write/read watch on the page buffer, started from `fn 0x0041c044`, the `.cmp` caller found by H51) instead of a fourth static pattern.
  - Pair: pair
  - Note (rule 15, 2026-11-09 PO): M9.11b done; re-opened. Prior blocker kept: page handed to walker by `OSM_TaskSend` reply (OSMDLL import 12, `fn 0x3f40ec`); no 16-bit swap loop in Navi.exe/OSMDLL sec0 (C-2547, C-2548). M9.11 is re-opened (was blocked on M9.11b); re-run precheck before dynamic work.
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

- [x] **M3.11c — The name accessor for a `POINT` record**
  - Status: done · Owner: task/m3.11c-point-name-accessor · Critical: yes
  - Result: EXP-2026-11-19-M3.11c-point-name-accessor-l3.md (done). `fn 0x003f632c(r4=db=page, r5=rec)` → name pointer and `fn 0x003f5e78` → length in words (EU2011; US2011 `0x0041ec8c`/`0x0041e7d8`) run in PySh4 with the slot table filled by the M3.22 writer (slot `+0x1c` = page, `+0x20` = the file's field dictionary, found once per `.DAT`). US2011 `POINT010` rec0 = `+0x5e`, 9 words, `HANA HEALTH CENTER`; M5.12 rename → `OSM2LEAF TEST POI1`; name + address (field 6) split the display text on 1000/1000 records per build; both negatives -1. The name is located by per-record field-length bytes, not by `ff ff`. Different-length renames break it (C-5117 → new M5.52). The text byte order in memory stays M3.11b. C-5110–C-5117.
  - Blocker (history, negative EXP kept): end-to-end PySh4 of the identified accessor
    (`0x003f632c`/`0x003f5e78` → `0x003f61bc`/`0x003f5d98` field 5) on record 0
    requires HDLMAP page context (`0x00d53500` handle table + indirect
    `*0x0055d8f0`) in compressed `.data` (sec1, C-2128); without context it
    faults (PySh4 `UnmappedAccess 0x0055d8f0`), so the Done-when name string
    return (`HANA HEALTH CENTER` / M5.12 `OSM2LEAF TEST POI1`) cannot be
    produced. VAs/args/chain identified and sub-accessors PySh4-verified.
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker VAs `0x0055d8f0` = IAT `OSMDLL!taskIdSelf` (import/binding/stub, not M1.2f) and `0x00d53500` = BSS sec1 +0x7f6500 (zero at load; find writer/runtime init, not M1.2f). Mixed classes explicit: `0x005628e8` is INIT sec1 +0x58e8 (needs M1.2f only if that VA is required by rerun) and `0x00840ba0` is BSS (result/page context). Rerun with va_class-aware preconditions (M3.22 writer + M9.35 IAT/BSS model) before claiming M1.2f.
  - Note (H49): `0x0055d8f0` is the `OSMDLL!taskIdSelf` import slot and
    `0x00d53500` is BSS (zero at load) — M1.2f cannot supply either.
    Unblock is now **M3.22** (who fills `0x00d53500`) + **M9.35** (bound IAT).
  - Unblock: **M3.22** + **M9.35** (H49, see note). Old wording: M1.2f/M8.E1 (readable `.data`/globals) or a stubbed HDLMAP page
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
  - Claims: C-5110–C-5119 (was C-2920–C-2929 (was C-2548–C-2549, overlap with M3.11b fixed by H24); fresh block for this run)

- [ ] **M3.13 — The `ADDRE` (address) reader**
  - Status: blocked · Owner: task/m3.13-addre-reader · Critical: yes · Pair: required
  - Blocker: C-971/C-972 (directory, cells), the block-1 bytes (coordinate id, point tokens, C-976) and the range item body (C-975) are neither mapped to a consuming instruction nor shown never-read (navigator review 2026-11-20).
  - Unblock: M3.32 (block-1 and item consumers) + M3.30 (search path: directory/cells/index).
  - Result: EXP-2026-11-20-M3.13-addre-reader-l3 (C-5930–C-5939; blocked, real progress). The reader is the generic `REFER001` field accessor: the `0x14e4` writer `fn 0x003fd390` (search type 2) stores page → `+0x14`/`+0x2c`, dictionary (= the schema block: `area code`, `street name`, `dndc-id`) → `+0x18`; `fn 0x003f61bc`/`fn 0x003f5d98` return the fields of 3,650 EU2011 and 57,180 US2011 factory records (all match `addre.py`), and of two edited blocks. `TT LL 00 ff` is the field-length block, `rec[2]`/`rec[3]` the word counts of block 1 and of the length-prefixed range items, record length `2*(w & 0x3ff)` (`c1` = `L ≥ 256`; 43,602/43,602 EU2011 blocks framed). `refer.md` holds the field → instruction table; not located: readers of the bytes inside block 1 and range items (M3.32) and of directory/cells/index (search path, M3.30). `fn 0x0040b358` is a path lookup.
  - Re-opened (rule 15, PO 2026-11-20): the `Unblock` below is met. The `0x00d53500` slot table is filled at run time by the M3.22 writer and M3.11c ran the `POINT` accessor on it (C-5110–C-5117); M9.38 lists the functions that read a decoded `ADDRE001` blob (C-3606) and M3.28 names both openers (C-4666, C-4670). What remains is this task's own `Done when` on `ADDRE`: bind the slots as M3.11c did, run `0x003f56bc`/`0x0040b358` on one record and name the fields read. Start from `python3 tools/read_watch_l3.py --help` and `python3 tools/vcard_l3.py trace`.
  - Note (M3.28, 2026-11-19): `ADDRE` has two openers, both run on the card: `0x003fbed8` with search type 2 and `0x004011a0(n)` → `ADDRE0<n+1>.DAT` (caller `0x00401ff8`, which also issues the read) (C-4666, C-4670). Tools: `python3 tools/name_loaders.py openers`, `python3 tools/vcard_l3.py trace`.
  - Note (M9.38, 2026-11-19): dynamic reader list on the decoded `ADDRE001` blob (48,852 B): `fn 0x003fbed8` reads `+0x68` (4-byte) and calls `GAP@0x003f9254` which reads `+0x7c` (4-byte); `fn 0x004125a8` reads `+0x8` (2-byte). `0x003f56bc` and `0x0040b358` read 0 bytes at these entries (both need the BSS `0x00d53500` slots bound — the same context M3.11c names), and `0x0040114e` stops on an FPU `IllegalInstruction` at `0x00401150`. C-3606, EXP-2026-11-19-M9.38-read-watch.
  - Blocker (history, negative EXP kept): `fn 0x003f56bc` (sec0) is confirmed as the sole 0xc000-class header
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
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker/binding VA `0x00d53500` = BSS sec1 +0x7f6500 (zero at load; find writer/runtime init, not M1.2f). Rerun with va_class-aware preconditions (M3.22/M9.35 context as applicable); keep M1.2f out unless an INIT VA is identified.
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
  - Claims: C-5930–C-5939 (was C-2180–C-2189; fresh block for this run)
  - Note (SE 2026-11-13): the pass-3 EXP `EXP-2026-11-12-M3.13-addre-reader-3` is the current record; its status line said "done (partial)" and was corrected to `blocked`. Its "never read" labels (C-970/C-975/C-977) are scoped to **sec0 literal pools**; `Navi.exe` sec1/sec2 (decoded by `nk_decomp`) were not searched, so do not read them as "the firmware never reads these".
  - Result: `EXP-2026-11-08-M3.13-addre-reader-2.md` (C-2180–C-2187, partial; refines `EXP-2026-11-06-M3.13-addre-reader.md`). Writer-implied native `u16` class-mask signature finds `fn 0x003f56bc` (Navi.exe sec0, `0x003f56ec`) — sole `*r5 & 0xe000 >= 0xc000` (`cmp/hs` literal `0xc000`, 1/82 loads) gate, accepts ADDRE `c0/c8/c1` (C-973 tag-class mapped). Resolves via `0x003f51e0` (`0x00d53500`, POINT family); callers `0x003f5d98`/`0x003f61bc`. C-970–C-972, C-974–C-977 + sequential `2*L`/token consumers not mapped (done-when not met). L3: `0x0040b358`→`-1`, `0x0040114e` FPU-unmodelled. `refer.md`/`firmware.md`/`reader-coverage.md`/`claims.md` updated.

- [ ] **M3.14 — `ZCODE` / `ICODE001` / `COORD001` readers**
  - Unblock: M3.23 (2026-11-20) candidates. `ICODE` (`python3 tools/callgraph.py rank g.json --edges e.json --depth 4 --family LCTBL=0x004125a8 --family ICODE=0x003f2cc0 --family REFER=0x003fbed8`): `0x00401e94`, `0x004082cc`, `0x00402690`, `0x003f6c88`, `0x003f0c7c`, `0x00407724`, `0x003f07f8`, `0x004078e4`, `0x003f08cc`, `0x00409ba0` (3 are C-4694 loaders). `ZCODE`/`COORD` have no static anchor of their own (ctx +124 = 11/12 in `0x003fbed8`; `COORD001` unnamed): shared REFER list `0x003f0aec`, `0x003fd690`, `0x003fbbac`, `0x0040dfa8`, `0x003fdd18`, `0x0040d704`, `0x0040da3c` (C-3546). Confirm with M9.38 / M3.29.
  - Status: blocked · Owner: task/m3.14-zcode-icode-coord · Critical: yes · Pair: solo
  - Blocker: two signature families fail in EU2011 `Navi.exe` (M3.23 candidate probe with a zero-buffer control; file-id literal scan), so no content-bound reader is located for `ZCODE0nn` or `COORD001` (`ICODE001` now has a field-to-reader map from the mount run). Done-when not met (C-5760, C-5761, C-5766).
  - Unblock: **M3.30** (drive the REFER search path with search type 11/12 and watch the `ZCODE` parser; probe `COORD001`). M3.30 itself depends on M3.29 (open), so the search-path run that issues `0x003fc0ec`/`0x003fc518` is what re-opens this task.
  - Result: EXP-2026-11-20-M3.14-zcode-icode-coord (negative for ZCODE0/COORD001, ICODE001 field map; done-when not met; C-5760–C-5767). Prior: EXP-2026-11-08-M3.14-reader-layout.
  - Note (M3.25, 2026-11-19): `ICODE001.DAT` and `ICADM001.DAT` are read during the mount run and the functions that load their bytes are listed in C-4694 (`datask_l3.py mount … --file REFER001`); positions are in the decompressed file.
  - Note (M3.28, 2026-11-19): openers found without M1.2f: `ZCODE` = `0x003fbed8` with search type 11/12; `ICODE001` = `0x003f2cc0`, reads through `0x003efe10`/`0x003f0400`/`0x003f2828`; `COORD001` has no name reference in `Navi.exe` at all (C-4666, C-4669, C-4677). The blocker on M1.2f no longer holds for the first two: reopen from these functions. Tools: `python3 tools/name_loaders.py openers`, `python3 tools/vcard_l3.py trace`.
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52).
  - Depends: — (M4.12 already decoded the layout from bytes; this task only
    looks for the consuming code)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` (M1.12) — build A
    has **0 compressed executable sections** (C-2128), so "not found" means the
    *signature* was wrong, not that the bytes are hidden. Test a structural
    signature derived from an L3 run or the writer's inverse, not the byte
    grammar in `refer.md` (that assumption is how M3.11's walker was missed,
    C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code.
  - Stop: after two signature families fail — then `blocked` + EXP listing the
    signatures tested (reached 2026-11-20: candidate probe + id-literal scan).
  - Goal: the region/index/coordinate tables decide where a generated
    Poland map lives; confirm their layout (C-110, C-1992,
    `coord-zcode-icode.md`) from the code.
  - Input: id table `0x00179338` (`ZCODE0`), `coord-zcode-icode.md`, M4.8c, M4.12.
  - Done when: `coord-zcode-icode.md` gives the reader VA per file and which
    fields each one uses, with VAs.
  - Claims: C-5760–C-5767

- [x] **M3.15 — The `LCTBL001` name-table reader**
  - Unblock: M3.23 (2026-11-20) candidates (`python3 tools/callgraph.py rank g.json --edges e.json --depth 4 --family LCTBL=0x004125a8 --family ICODE=0x003f2cc0 --family REFER=0x003fbed8`): `0x0040dd40`, `0x0040de98` (rank 2; the M9.38 reader, C-3607), `0x004125a8`, `0x00409cc8`, `0x0040b358` — the whole loop set below `0x004125a8` is these five (C-3544). Next is the record walk behind `0x003fc0ec`/`0x003fc518` (search type 1), which only a run separates (M3.29).
  - Status: done · Owner: task/m3.15-lctbl-reader · Critical: yes
  - Note (M3.28, 2026-11-19): `LCTBL001.DAT` is opened by `0x003fbed8` when the search type is 1 and ctx +104 is `0x14e4` (run on the card, C-4667), besides the literal in `0x004125a8`. The record walk is behind the read issuers `0x003fc0ec`/`0x003fc518`. Tools: `python3 tools/name_loaders.py openers`, `python3 tools/vcard_l3.py trace`.
  - Note (M9.38, 2026-11-19): dynamic reader list on the plain `RDSTM001/LCTBL001.DAT` (7,489,024 B): of the four candidates `0x003f020c`/`0x0040dd40`/`0x0040de98`/`0x0040b358` only `fn 0x0040de98` (`GAP@0x0040de96`) reads it — six reads, widths 4/4/2 at offsets `+0x8/+0x4/+0x2` (read twice, two passes) — plus the shared header read `0x004125a8` `+0x8` (2-byte). C-3607, EXP-2026-11-19-M9.38-read-watch.
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52). The two character-set strings found in sec1 `INIT` (M3.24) are a lead for the name encoding.
  - Former blocker (resolved 2026-11-20): H49 reopen (sec1 "helpers" are IAT imports `OSMDLL!OSM_isSender`/`OSM_Printf`, C-3443, not compressed code): two writer-inverse signature families derived from `lctbl_records.py`/`lctbl_names.py` parse invariants of stock `LCTBL001.DAT` (SHA-256 `8cab1775…`) — S1 marker `mov.b @(2,Rm),R0` + `cmp/eq #1,R0` (40 B, from marker@+2==0x01) and S2 four slot-length reads `mov.b @(d,Rm),R0` d∈{3,4,5,6} same base (80 B, from +3..+6) — scanned Navi.exe sec0 exec plain (5,553,430 B, VA `0x00011000`) and OBJDLL.dll sec0 exec plain (349,755 B, VA `0x03481000`) with 0 hits each (C-2207). Reachability from `fn 0x004125a8` traced through resolved IAT/non-import CODE callees and `0x00413a6c`/`0x00412ac0`→`0x00404994` inflate path without locating record parsing/string decode; `0x003bc960` is TMC/RDSTM decoding (C-2208). No cited blocker VA is `INIT` (`va_class.py`), so M1.2f not justified. Done-when unmet (no reader VAs, encoding assumed by code UNKNOWN).
  - Former unblock (resolved 2026-11-20): **M3.23** (candidate readers by call-graph reachability from the access path; its own deps are M1.20 + M3.24, both open) confirmed by **M9.38** (which function reads the page buffer). `M1.2f`/`M8.E1` are superseded (H51: `nk_decomp.py` decodes 245/245 build-A sections) and must not be named as a blocker (H81 closes them; verified by `va_class.py` that no `INIT` byte is needed). The earlier "derive another signature" family is retired per AGENTS.md.
  - Former blocker (history): the record walker and string decoder were thought reached only through compressed `Navi.exe` sec1 helpers (`0x0055d924`, `0x0055d954`) (C-2200–C-2206); diagnosis superseded by H49/C-3443.
  - Note (2026-11-20): located. Record walk = the C-884 field directory `0x003f61bc` + `0x003f56bc`/`0x003f57a8`/`0x003f5e10` (length `0x003f5d98`); twelve extractors `0x003f66b8`, `0x003bc028` (field 1, road number), `0x003bc194` (field 2, road name), `0x003bc300`, `0x003bc470`, `0x003f6734`, `0x003f6780`, `0x003f67cc`, `0x003f6818`, `0x003f6864`, `0x003bc748`, `0x003f68bc` called by `0x003bc960`; the `0x003f60xx` thunks are the length (`0x003f5d98`) calls, the accessor thunks are `0x003f6704`(1)/`0x003f6710`(2)/`0x003f671c`(3)/`0x003f6728`(4)/`0x003f68b0`(10); string decode `0x003ca858(buf,len,1)` swaps 16-bit high-byte-first, encoding single-byte CP_ACP, executed with a structural control (`lctbl_string_decode.py`). `0x0040de98` is the page-cache registration, not the walk (C-2205, C-2208, C-2209). Executed end-to-end read is M9.24.
  - Result: EXP-2026-11-20-M3.15-lctbl-reader (done; walk + decode VAs and CP_ACP encoding named, VAs-per-field table). Prior: EXP-2026-11-10-M3.15-lctbl-reader-reopen (negative), EXP-2026-11-08-M3.15-lctbl-reader.
  - Depends: — (M3.7 located the `LCTBL001.DAT` load at `0x004125a8`; H49: the "compressed" callees were imports)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` / `--module OBJDLL.dll` (all executable sections readable, C-2128). Derive signatures from writer-inverse/L3 observation, not doc grammar.
  - Scope: build-A executable sections (all readable); `.data` tables only via a pointer found in code. `Stop:` after two signature families fail — `blocked` + EXP listing signatures tested.
  - Goal: Polish street/place names go through this table (M4.18 framing, M3.9 collation); confirm framing and encoding from the code.
  - Done when: `refer.md` (or `rdstm.md`) names the record-walk and string-decode VAs and states the encoding the code assumes.
  - Stop: after two signature families (named, with source) fail in sec0 and `OBJDLL.dll` — `blocked` + EXP; a cited VA must carry its `va_class.py` class, and only an `INIT` address may name M1.2f.
  - Claims: C-2200–C-2209

- [ ] **M3.16 — `INTER` / `FRWAY` readers**
  - Unblock: M3.23 (2026-11-20) candidates, shared with `ADDRE`/`ZCODE` because the family is ctx +124 at run time (`python3 tools/callgraph.py rank g.json --edges e.json --depth 6 --family REFER=0x00400014,0x004000e8,0x004001bc,0x004003f4,0x004005f8 --family POINT=0x003ffe80 --family LCTBL=0x004125a8 --family ICODE=0x003f2cc0`): `0x003f0aec`, `0x003fd690`, `0x003fbbac`, `0x0040dfa8`, `0x003fdd18`, `0x0040d704`, `0x0040da3c` (library `0x0054233c`/`0x005468d4`/`0x0054705c` dropped); the read issuer `0x003fc518` is rank 15 (C-3545, C-3546). Split per family with M3.29.
  - Status: blocked · Owner: task/m3.16-inter-frway · Critical: no
  - Note (M3.28, 2026-11-19): openers run on the card: `0x003fbed8` with search type 4 (`INTER`) and 3 (`FRWAY`); the reads come from `0x003fc0ec` and `0x003fc518` (C-4666). The two signature searches that found nothing can be replaced by following those two functions. Tools: `python3 tools/name_loaders.py openers`, `python3 tools/vcard_l3.py trace`.
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52).
  - Blocker: no content reader VA consuming the real INTER/FRWAY 12-byte table (BE `0xffff` key at +0, `length`/`offset` +6/+10) or blob fields was found in decodable build-A Navi.exe sec0 (5,553,664 B, 0 compressed exec sections, C-2128) after four halfword signature families (only `0x00392122`, a byte walker) and an L3 watch of the 11 M3.23 candidates (context reads only); consumed-field mapping unknown (C-2215–C-2219). Shared REFER001 access path is confirmed (C-2210).
  - Unblock: **M3.29** (per-family runtime split of the M3.23 candidates) confirmed by **M9.38** (which function reads the page buffer). `M1.2f`/`M8.E1` are superseded (H51: `nk_decomp.py` decodes 245/245 build-A sections) and must not be named as a blocker (H81 closes them; verified by `va_class.py` that no `INIT` byte is needed). The earlier "derive another byte signature" family is retired per AGENTS.md (H51).
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
  - Stop: (H53 backfill of the Scope sentence as a field) when M3.29's per-family split hands over the INTER/FRWAY candidates, watch them in one L3 run on the factory INTER001 page; if none reads `0x1108`/`0x1110`, stay `blocked` with the watched list in an EXP — no fifth byte-signature family (H51).
  - Done when: the reader VAs and consumed fields are in `refer.md`.
  - Claims: C-2210–C-2219
  - Result: `EXP-2026-11-20-M3.16-inter-frway.md` (blocked; done-when not met). **Layout corrected:** the 12-byte record at `0x1108`/`0x1110` is big-endian (`u16 key` +0 `0xffff`=term, `u16 0` +2, `u8 id` +4, `u8 flag` +5, `u16 length` +6, `u16 b8` +8, `u16 offset` +10), all 10 factory shards conform (`tools/inter_table.py check`, exit 0); the old LE/11-byte/+8 form is refuted 0/177 (`tools/inter_table.py refute`), C-2215/C-2216. **Reader still not found:** four halfword signature families over Navi.exe sec0 (5,553,664 B, 0 compressed exec, C-2128) give only one f3 candidate `0x00392122`, a byte `@(1,Rm)`/`0xff` walker, not the u16-key table (`tools/inter_reader_scan.py scan`, C-2217); L3 watch of the 11 M3.23 candidates on the factory INTER001 page reads only context/`+0x0`, none touches `0x1108`/`0x1110` (LCTBL `0x0040de98` positive control PASS, C-2218). Consumed fields UNKNOWN (C-2219). Earlier `refer.md` + C-2211/C-2213 updated.
  - Result (r2): `EXP-2026-11-08-M3.16-inter-frway-readers-r2.md` (negative/blocked). Shared REFER001 access path confirmed (C-2210; `INTER0`/`FRWAY0` in volume-id table `0x00179338` ~VA `0x0017934c`/`0x00179354`, descriptor `0x14e8` `fn 0x004125a8` → `REFER001`+`INDEX003.DAT`, name-builder `fn 0x003fbed8`); two writer-inverse families found 0 candidates (C-2211). `refer.md` INTER/FRWAY sections and `claims.md` C-2210–C-2214 updated.

- [ ] **M3.18 — `ICADM0nn` / `ZIPFR001` readers (H11 G2)**
  - Note (2026-11-20, rule 15): re-opened by **M3.23** (done); the r3 run is in EXP-2026-11-20-M3.18. M3.23 gave no static root of the family's own — `ICADM001` loads sit in the `ICODE` list below `0x003f2cc0` (C-4694: `0x003f0c7c`, `0x003f07f8`, `0x003f08cc`, `0x003eff20`), and `0x003f1640` (C-2381) adds no candidate of its own.
  - Status: blocked · Owner: task/m3.18-icadm-zipfr · Critical: no
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52).
  - Depends: — (M3.11/M3.13 show the access-path pattern for `REFER001`
    families and the same compression wall)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` (M1.12) — build A
    has **0 compressed executable sections** (C-2128), so "not found" means the
    *signature* was wrong, not that the bytes are hidden. Test a structural
    signature derived from an L3 run or the writer's inverse, not the byte
    grammar in `refer.md` (that assumption is how M3.11's walker was missed,
    C-2129).
  - Scope: build-A executable sections (all readable); `.data` tables only via
    a pointer found in code.
  - Stop: after two signature families fail — then `blocked` + EXP listing the
    signatures tested (reached: three families, r3 EXP).
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
  - Note (2026-11-20, r3 after M3.23): the **open/descriptor** path is now
    located for both families. `ZIPFR001.DAT` (`0x00178e08`) is row 4 of a
    24-byte sec1 descriptor table `0x00564160` (`0x005641c0`, style 16, id
    `0x040c`), loaded by `0x003f7d94`/`0x003f7f40`/`0x003f7b20`, looked up by
    `0x003f7ae4` (`(16,0)`→4), issued by `0x003f7b54`/`0x003f7c38` →
    `0x0040b358`. **C-2382 retracted.** ICADM reads still go through
    `0x003f72cc` (`0x003eff20`, `0x003f17a4`, `0x003f2bc4`, `0x003f0c7c`).
    Neither family's **field-consuming** reader is located.
  - Blocker (2026-11-20, third signature family): reader VAs + consumed fields
    still not named. The record consumer is registered at run time — the
    static `+12` handler slot of the `0x00564160` rows is empty and filled by
    `fn 0x003f7f40` — or the firmware only carries the search result to the
    caller; no 14-byte (`add #14`) ZIPFR stride and no 462-byte (`add #0x1ce`)
    /`0x00e7` ICADM stride in the located subtree. `refer.md` and matrix rows
    14–15 updated to `partial` (open path only).
  - Unblock: **M3.29 / M9.38** — the run-time observation of the completion
    for the ZIPFR/ICADM search (`0x003f7f94`/`0x003f7b54` with the map-file
    task live; M9.38 read-watch) that names the handler written into `+12` (or
    proves copy-only with a positive control); then re-run the field scan over
    that handler. Not M3.23 (done).
  - Result: EXP-2026-11-20-M3.18-icadm-zipfr (blocked; open/descriptor path
    located and confirmed by run — C-2386–C-2389; C-2382 retracted; field
    readers not located).
  - Claims: C-2380–C-2389

---


- [x] **H40 — L1/L2 generated-fixture contract: deterministic in-process fixture + coherent ZE0 card/tree builder (no vendor data)**
  - Status: done · Owner: task/h40-generated-fixture-contract · Critical: yes
  - Depends: H26; H103 (the `--generate-fixture` primitive) and H105 (its `--break` control) — the L1 CI row cannot exist before the tree can be built and made to fail
  - Note (QA 2026-11-20, cycle 18): the builder half exists — `python3 tools/cardcheck.py --generate-fixture DIR --json OUT` (H103) writes a vendor-free tree, byte-identical over two runs here, 6 checks PASS and 2 SKIP. `python3 tools/l1l2_fixtures.py --require-covered` still exits 1 because the registry row `l1.synthetic.cardcheck` says "no vendor-free synthetic ZE0 card builder". What is left of this task is that row (run the H103 tree) plus H105's broken tree as its negative.
  - Goal: close H26 gaps (`L1 synthetic`/`L2 tile` NOT COVERED where feasible) with a tiny deterministic in-process fixture representing generated content (roads/names/POIs/geometry) and a coherent ZE0 card tree/image that `cardcheck.py --root/--image` and targeted L2 round-trips can run on in CI (no network, no OSM download, no vendor data).
  - Scope: test infrastructure only. Procedural/committed fixture (no vendor dump, no downloaded OSM extract) and a minimal builder producing coherent DRSTR/MMAIN/tile level tables/headers/REFER001/top-level layout as current tools support. Do not claim firmware acceptance (rule 13); no full M5 compiler coverage.
  - Input: `tools/l1l2_fixtures.py`, `tools/cardcheck.py`, `tools/mkcard.py`, `tools/drstr_ze0.py`, `tools/tilewriter.py`/harness, `tools/imgpatch.py`, `tools/one_tile_pipeline.py` (`--synthetic` already builds a no-vendor card tree, but its `MAPAL001` tile set is not `cardcheck`-coherent — QA 2026-11-17 measured `cardcheck rc=1`, section 2 levels 2/4/5 and section 4 level 1 not in `MMAIN`); AGENTS data rules.
  - Done when: `python3 tools/<name> --selftest` builds the fixture in a temp dir, runs `cardcheck.py` and reports L1 PASS/FAIL per check (JSON), and runs >=1 coherent synthetic L2 round-trip (tile/DRSTR/POI) where supported; CI-safe/deterministic; H26 registry gains runnable entries only where truly covered, else honest NOT COVERED with updated reason. **Negative control:** the same row must fail on a broken tree — `cardcheck --generate-fixture … --break <kind>` (H105) exits 1 and names the check the good tree passed, so `l1l2-fixtures.yml` cannot go green on a checker that stopped checking.
  - Stop: if coherent MMAIN/tile/DRSTR cannot be produced without vendor bytes, deliver the smallest coherent subset with explicit NOT COVERED per uncovered file/feature and follow-up tasks naming missing writer/structure; never fake PASS.
  - Claims: C-3270–C-3279
  - Result: EXP-2026-11-22-H40-generated-fixture-contract (C-3270–C-3276): H40's generated-fixture contract is already in place on origin/main — H103 --generate-fixture tree is vendor-free, 6 PASS/2 SKIP, byte-identical over two runs; H105 --break tile-level-in-mmain tree is rc=1 FAILing mmain (the id the good tree passed); L2 drstr/cmpind/tile/POI rows PASS; l1l2_fixtures --selftest OK (32 checks) and --require-covered rc=0 so the H26 l1.synthetic.cardcheck row is runnable; honest gaps stay NOT COVERED. Closed as the verification row it became; gate 5 pass/0 fail/0 skip.

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
  - Depends: H27, H41, H28, H55
  - Goal: make the per-level progress signal visible on every PR/push: publish `progress.json/md` (H27 schema) plus H41 per-file/per-feature matrix as artifacts/job summaries.
  - Scope: workflow changes only (extend existing workflows or add `progress.yml` as appropriate); no vendor data, no IMG256/ROOT, no QEMU/M8 run in PR gate, no L5 bench execution. Integrate H28 L3 synthetic summary when H28 lands. Local/vendor checks listed as LOCAL-ONLY/NOT RUNNABLE, never executed in PR gate.
  - Input: `tools/progress_report.py`, H41/l1l2_fixtures JSON, `tools/l3check.py --build-corpus --json` (post-H28), `tools/realcheck.py` classification; `.github/workflows/*`.
  - Done when: PR run uploads/prints progress including L1/L2 generated-fixture per-file/per-feature counts, L3 target counts with firmware-proof separated from synthetic/harness (rule 13, L3 fragment/L4-emu/M8/L5-bench mapping per AGENTS.md), and L4 (M8 full-system emulator) / L5 (car/bench) explicit manual status where recorded; local-only checks in a separate "not run in CI, vendor data required" section; EXP links one CI run and maps fields to H27 rule-13 table.
  - Stop: if cross-job artifact passing is unreliable, generate progress in jobs that have inputs and mark aggregation as a follow-up, but still publish per-level summaries.
  - Claims: C-3290–C-3299

- [ ] **H43 — L3 generated-fixture corpus and per-reader progress for "our data" (extends H28)**
  - Status: open · Owner: — · Critical: no
  - Depends: H28, H40, M9.12 and runnable M9.2/M9.14/M9.17/M9.18/M9.24 reader targets
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

- [x] **M3.22 — Who writes the `0x00d53500` table (HDLMAP / RDSTM schema)**
  - Status: done · Owner: task/m3.22-d53500-writer · Critical: yes
  - Note (H51, 2026-11-11): **re-opened (rule 15): its Unblock M9.35 merged on 2026-11-10 and the board did not turn it back.** Two corrections before the L3 run: `0x00412bee`→`fn 0x00412ac0` is not a function — it is inside `fn 0x00412ac0` (pdata: prologue 18 B, length `0x1a0`), whose only static caller is `fn 0x00413a6c` (`jsr` at `0x00413af4`) — enter there, with the frame the caller builds; and the engine fix of H51 changes any run that executes `mov.b/mov.w R0,@(disp,Rn)`. Check every writer VA with `python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe VA…` first. The `INIT` bytes of sec1 are readable now (M1.19/M3.24): a table base loaded from there is no longer a blocker.
  - Blocker: Done-when unmet (M9.35 not merged): all 33 load sites/20 functions classified (11 READ, 22 STORE_WRITE) with opcode evidence and back-trace of stored values (zero-clears in `fn 0x0040dfa8/0x00415fe8/0x0040e28c`; populate/copy in `fn 0x00412ac0`, `fn 0x003fcbf0`, `fn 0x003fd390`, `fn 0x003fe774`, `fn 0x003faf04`, `fn 0x003fc9c8`), but no L3 run or writer-inverse reproducing >=1 entry and no definitive entry size/count/per-field schema provenance without IAT-bound runtime context.
  - Depends: — (H49: the table is BSS, C-3442; its content is produced at run time, so M1.2f cannot give it)
  - Goal: name the function(s) that fill `0x00d53500` and say what they copy there and from where (file header, `MMAIN001`, a loader of the `REFER`/`RDSTM` page handles), so M4.16b can read the schema and M3.11c can build the page context the name accessor needs.
  - Precheck: `python3 tools/va_class.py IMG256 --module Navi.exe 0x00d53500` → `BSS`; `python3 tools/sh4xref.py IMG256 Navi.exe --image-start 0x200200 --to 0x00d53500` → 33 loads (H49), the most frequent in `fn 0x00415fe8` (6) and `fn 0x0040dfa8` (6).
  - Scope: the ~20 functions that load `0x00d53500` in `Navi.exe` sec0; classify each load site as **store** (`mov.l Rm,@(disp,Rn)` / `mov.l Rm,@Rn` with `Rn` derived from the table) or read. Signature source: the store instructions themselves (not the format doc). Follow the stored values back to their source (a file read through `fread` import slot `0x0055d1a0`, or another BSS global).
  - Input: EXP-2026-11-08-M4.16b-rdstm-field-walk, EXP-2026-11-08-M3.11c-point-name-accessor, EXP-2026-11-08-M3.13-addre-reader-2 (follow-up "bind `0x00d53500` table slots … by static init xref"), EXP-2026-11-08-M1.12-reader-precheck (follow-up "store search").
  - Done when: an EXP names the writer VA(s), the table's entry size and count, and the source of each field, with one L3 run (PySh4, after M9.35, or a direct stub) or a writer-inverse check reproducing at least one entry from a factory file; `docs/format/firmware.md` gets the table layout.
  - Stop: after the store classification of all load sites plus one back-trace family without a source — write the EXP `blocked` with the store list (it is the input for an L3 run of the writer in M9.35).
  - Unblock: M9.35 (harness: zero BSS + IAT bound to stubs/named logging stubs) — run populate writers `fn 0x00412ac0` (ctx r8 handle words), `fn 0x003fd390/0x003fcbf0/0x003fe774/0x003faf04/0x003fc9c8` (ctx r10/r11/r15 structures) with sec0 mapped from IMG256 `92aa525d…` to observe slot mutations and reproduce >=1 entry; then derive entry size/count/per-field provenance.
  - Result: EXP-2026-11-10-M3.22-bss-table-writer.md (blocked). 33/33 sites classified (11 READ, 22 STORE_WRITE) with VA/opcode evidence; writers named: clear/init `fn 0x0040dfa8`, `fn 0x00415fe8`, `fn 0x0040e28c`; populate/copy `fn 0x00412ac0`, `fn 0x003faf04`, `fn 0x003fc9c8`, `fn 0x003fcbf0`, `fn 0x003fd390`, `fn 0x003fe774`. Back-trace: zero constants, context struct fields `@(20/24,rX)` from `@r10/@r11/@r15`, call result `0x0040f168`, handle-word copies from r8 context, global `@(*0x014a9928)->+20`. Entry size/count and per-field schema source remain UNKNOWN (no L3/writer-inverse). Firmware note added (provisional/blocked). C-3460–C-3468.
  - Result: EXP-2026-11-19-M3.22-d53500-writer-l3.md (done). The table is one structure of 4-byte page-pointer slots (EU2011 `0x00d53500`, 46 words / `0xb8` B; US2011 `0x00c81100`, 44 words / `0xb0` B); populate writers = cases of the task-message switch `fn 0x003ff6a0` (EU2011) / `0x0042780c` (US2011) on `@(ctx+104)` `0x14cc..0x14f0` (`tools/d53500_writer.py cases`/`slots`). PySh4 run of `fn 0x003faf04` (EU2011) / `0x00423ba8` (US2011) on type `0x14ef` writes slot `+0x1c` = `*(*(G)+20)` (`G` = `0x014a98e0` EU2011 / `0x01319780` US2011); the real dispatcher on that table reads the factory `POINT010` page and returns record 1 at `+0x4e` (EU2011) / `+0x80` (US2011), equal to the walker alone; type `0x14f0` leaves `+0x1c` zero (negative). The slots hold pointers, not on-disk fields. Next hop (who fills `G+0`) is a follow-up in the EXP. C-5120–C-5127.
  - Claims: C-5120–C-5129 (was C-3460–C-3469; fresh block for this run)

---

- [x] **M3.23 — Static call graph of `Navi.exe` (pdata + pools + dispatch tables), and readers found by reachability**
  - Status: done · Owner: — · Critical: yes
  - Result: `docs/experiments/EXP-2026-11-20-M3.23-callgraph-readers.md` (C-3540–C-3547). `callgraph.py` joins register state across branches (+668 direct edges, 0 removed; unresolved 395 → 204) and gains `loops` and `rank`; known edges and the `.cmp` chain from table `0x0017ab38` (`0x00419c38`) down to `fopen`/inflate reproduced. Stop not met (2.9 % unresolved). Ranked lists per family: `LCTBL` confirmed reader `0x0040de98` at rank 2; `ICODE` 3–4 of 10 are C-4694 loaders; `POINT` top 3 are known record functions, but the walker `0x003f5194` is 15–18 (weak recall). `ADDRE`/`INTER`/`FRWAY`/`ZCODE`/`COORD` share one list: the family is ctx +124 at run time. Follow-up M3.29.
  - Note (H112, 2026-11-19): **rebuild the graph before using it.** The first `callgraph.py` decoded literal-pool words as instructions: 2,201 of 22,867 EU edges were false (M3.26 and M3.27 each caught one by hand). Fixed, with a selftest case; corrected numbers in C-4620. Imports by ordinal are now named. What is left of this task: (a) table edges (M3.24), (b) the reachability report per file family — start it from the name loaders of C-4627 (M3.28), not from byte signatures.
  - Note (H101, 2026-11-17): **the core exists: `tools/callgraph.py`** (`build`, `callers`, `callees`, `reach`, `users`, `path`, `stats`; `--selftest` 6 cases). `Navi.exe` EU2011: 9,000 nodes (1,404 leaf targets), 22,867 direct edges, 7,721 import edges, 589 unresolved indirect calls, 956 functions with no static caller; US2011: 8,890 / 22,119 / 525 / 970. It reproduces `0x0041c044 → 0x0041c990 → 0x0041c7dc → … → 0x00542250`. What is left of this task: the `loops` query, the map DLLs, and the ranked reader candidates per family. Only 589 calls are indirect — the `Stop` condition (30 %) is far away: in the `REFER` subtree below `0x004125a8` it is 47 unresolved in 223 functions.
  - Depends: M1.20 (function table), M3.24 helps (indirect edges)
  - Goal: stop searching readers by guessed byte signatures. Five tasks (M3.14, M3.15, M3.16, M3.18, M3.2b) ended at "access path found, record walker not found, N signatures 0 hits". With exact function boundaries the question becomes a graph query: which functions are reachable from the family's access path, read memory byte- or word-wise in a loop, and are not shared by the other families.
  - Precheck: `python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe 0x0041c990 0x0041c044 0x00413a6c` → three `START`; `python3 tools/sh4xref.py IMG256 Navi.exe --image-start 0x200200 --to 0x0041c7dc` → one caller (`fn 0x0041c990`, `jsr` at `0x0041ca5a`).
  - Scope: new `tools/callgraph.py` (`--selftest`): nodes = pdata records + called leaf gaps; edges = `bsr`/`bsrf` targets, `jsr @Rn` whose `Rn` was loaded from a literal pool in the same function, tail `jmp`, import calls through the IAT (named with `cerom.py imports --resolve-with 0x3e00200`); optional indirect edges from M3.24's tables. Queries: `callers VA`, `callees VA --depth N`, `path A B`, `reach VA --imports` (which imports a subtree can call), `loops VA` (functions in the subtree with a backward branch around a `mov.b`/`mov.w @Rm+` read). `Navi.exe` first; the map DLLs after.
  - Input: `tools/sh4xref.py` (pool resolution), `tools/sh4dis.py`, `nk_decomp.py pdata`; known edges for the self-check: `0x0041c044 → 0x0041c990 → 0x0041c7dc → inflate (0x00542250)`, `0x00413a6c → 0x00412ac0`, `0x003f5cdc → 0x003f5194`; REFER access path `0x004125a8`, `0x003fbed8`, `0x0040b358`; file-open strings `0x0017a1f8` (`LCTBL001.DAT`), `0x0017a118` (`INDEX003.DAT`).
  - Hints: an unresolved `jsr @Rn` is data too — count them per function; a function with many is a dispatcher and its table is in sec1 `INIT` (M3.24). For each family take the subtree below the function that loads the file-name string, subtract the subtree shared with the other families, and rank what is left by "has a read loop". For `LCTBL` the candidates below `0x004125a8` are `0x003f020c`, `0x0040dd40`, `0x0040de98`, `0x0040b358` (EXP-2026-11-10-M3.15). Confirm a candidate dynamically with M9.38 before calling it a reader.
  - Done when: the tool reproduces the known edges; the EXP gives, for `POINT`, `ADDRE`, `LCTBL`, `INTER`/`FRWAY`, `ZCODE`/`ICODE`/`COORD`, a ranked list of at most ten candidate reader functions each, with the query that produced it; the `.cmp` chain is extended upward from `0x0041c044` to the function that opens the file (answers M3.2b); M3.15/M3.16/M3.18/M3.14 get an `Unblock: M3.23` candidate list in their blocks.
  - Stop: if more than 30 % of calls in the REFER subtree are unresolved indirect calls, stop and do M3.24 first.
  - Claims: C-3540–C-3549

- [x] **M3.24 — Dispatch tables in `Navi.exe` sec1 `INIT`: who is called indirectly**
  - Status: done · Owner: task/m3.24-sec1-dispatch-tables · Critical: yes
  - Result: `docs/experiments/EXP-2026-11-19-M3.24-fptables.md` (C-3550–C-3559), new `tools/fptables.py`. EU2011: 69 tables (62 sec0, 7 sec1), 481 of 1,167 uncalled functions are entries, but only 21 of 395 unresolved `jsr @Rn` are table calls. No table holds a POINT/ADDRE/LCTBL reader; `0x0017a0a4` (message map, `fn 0x004124dc`) sits 1–2 calls above `0x004125a8`, `0x00412ac0`, `0x003fbed8`. `Lv*` block is data with no code pointer and no direct reference. Table list in `docs/format/firmware.md`; `--edges` (1,113) ready for M3.23.
  - Note (H112, 2026-11-19): corrected census (C-4623): 1,167 EU2011 functions have no static caller; 1,110 of them occur as an aligned word in sec0 and 57 in sec1. Unresolved `jsr @Rn` are 395 in 258 functions (not 589). The work is now small and mechanical: find runs of ≥ 3 consecutive code pointers in sec0 rodata (`0x00011000…0x0032ed9c`), find the function that loads each run's base (`sh4xref --to`), add `table` edges to `callgraph.py`. M3.26 already did this by hand for the two tables of the map-file task (`0x0017a888`, `0x0017ab38`) — use them as the positive control.
  - Note (H101, 2026-11-17): **H51 gave a wrong count — corrected (C-4283).** Of the 6,052 pointers in sec1 `INIT` only 281 point at code (163 distinct targets); 5,771 point at strings and constants in sec0 below `0x0032ed9c`. The function-pointer tables are mostly in **sec0**, which was always readable: of the 956 functions with no static caller, 914 appear as a 32-bit word in sec0 (a pool literal passed as a callback, or a table), 42 only in sec1 `INIT`, 1 nowhere. So: scan sec0 for runs of ≥ 3 consecutive words that are pdata `START`s — those are the tables — and tie each to one of the 589 unresolved `jsr @Rn` sites. The functions with the most unresolved calls are `0x003a2b94` (49), `0x004d78b4` (41), `0x0032efa8` (25, calls the file-layer dispatcher `0x00417924`), `0x004c09dc` (19).
  - Depends: — (H51: sec1 decodes; M1.19 gives the cached bytes)
  - Goal: the 98,330 stored bytes of sec1 contain 6,052 words that point into the code range (H51), i.e. function-pointer tables. "No static caller" (M3.2b pass 1/2, M3.11 "indirect call via `.data`") and the run-time table at `0x00d53500` are explained by them or not — find out.
  - Precheck: `python3 tools/nk_decomp.py section IMG256 --module Navi.exe --index 1 -o sec1.bin` → `r0=0x1801a`; count of 4-byte-aligned words `w` with `0x0032ed9c ≤ w < 0x00558300` in the first `0x1801a` bytes = 6,052.
  - Scope: sec1 `0x0055d000…0x0057501a` of build A (skip the IAT, the first `0xd38` bytes). Cluster consecutive code pointers into tables; classify each pointer with pdata (`START` / `INSIDE` / `GAP`); for each table find the sec0 code that loads its base (`sh4xref --to TABLE_VA`, and bases reached as `base + index*4`). Not: C++ object semantics.
  - Input: the pointer density per 4 KiB page of sec1 from H51 (pages 0–9 hold 5,100 of them, pages 19–23 the rest); ASCII strings in the same bytes: `Lv1_O`, `Lv2`, `Lv4`, `Lv1_D/TOP`, `Lv5` (map-level names next to pointer tables — a lead for the tile/`LEV3456R` reader M3.5/M3.6), `Dummy category`, and two character-set strings (`1234567890ABC…`, `Y'-&_+/()@#?!., `) that look like the name-search keyboard (a lead for the `LCTBL`/POI name encoding, M3.15).
  - Hints: a table whose entries are all `START` and whose base is loaded right before `jsr @Rn` with a scaled index is a dispatcher: record `(table VA, count, index source)`. Tables referenced from the functions that touch `0x00d53500` (`fn 0x00412ac0`, `0x003fcbf0`, `0x003fd390`, M3.22) are the per-family reader vtables the board has been looking for. Check `0x005628e8` (M3.11c's `INIT` fallback pointer) first — it is in page 5.
  - Done when: `docs/format/firmware.md` lists the tables (VA, entries, user function, guessed role) and the EXP answers: is there a table that contains the `POINT`/`ADDRE`/`LCTBL` readers, and which function indexes it; the `Lv*` table is tied to a function or shown unused.
  - Stop: after the table list; decoding what each callee does belongs to the M3 family tasks.
  - Claims: C-3550–C-3559

- [x] **M3.25 — The tile reader's *entry* VAs: one runnable tile target so L3 can read the file L2 writes**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes · Pair: required
  - Result: `docs/experiments/EXP-2026-11-19-M3.25-tile-reader-entry.md` (C-4680–C-4699); `tools/datask_l3.py` (`tables`, `mount`, `--selftest`). There is no `(tile, dst)` entry: tile bytes reach the firmware as read completions. EU2011: task entry `0x003ebfb4`, dispatcher `0x003ebee8`, completion `0x003f72e4` → by request tag `0x0040b8b4` (header), `0x0040c308` (level directory), `0x0041597c` (data block), each with `r4` = message, return not used. The tool runs the data-access task next to M9.44's map-file task and carries their messages: on the EU card the firmware mounts by itself (46 tile files, 31 reads) and its own parsers load bytes of `LEV3456R`, `B48R068R` and `B28R070R` (header `0xfa`/`0x1ac`/`0x800`, two directories; data blocks on the first two). Two controls on a changed `B28R070R` change the next read (`0x803`) or the loads (`0x1ac`). `targets.json` reason now points at M9.13. Not done: a data block of `B28R070R` (needs map request `0x14b5`), fields inside directory/blocks, the US build.
  - Note (M3.28, 2026-11-19): tile reads use the same path as every other file: opener → control block → wrapper `0x003f7384`/`0x003f73dc` → `0x003f6c88` → `0x0041841c`. Callers of the wrappers in the tile module: `0x0040a474`, `0x0040a558`, `0x0040bda4` (C-4664). Hook `0x003f6c88` in `vcard_l3.py trace` to see a tile reader's requests.
  - Note (M9.44, 2026-11-19): the file side now runs. `tools/vcard_l3.py` serves read requests with the firmware's own queue and worker (`Session.request(file id, offset, length)`), so the tile target can be built as: run the client chain (`0x0040b850` …) until `OSM_TaskSend`, decode the 48-byte request with the record table in `firmware.md` ("The read API"), serve it, write the completion message (id `0x04a0`) and continue the client at its message handler. The first request the client makes for `MAPAL001/B28R070R.DAT` (id `0x00030001`) is the tile reader's first read (C-4634, C-4639, C-4640).
  - Note (H112, 2026-11-19): **the H101 note below is wrong in three places (C-4622).** The renderer/router subtrees have 26 callees each, not 48; they import no `CreateFileMappingW`/`MapViewOfFile`; the tile is not memory-mapped there. With M3.27's negative this changes the task: `0x00425f40`/`0x004266ec` look like *request* functions (mesh id from `STD_PntData_getL1Mesh*` and `OBJ_CarPos_read`, then `OSM_TaskSend` in `0x0041ee14`), not parsers (C-4628, hypothesis). Start from the file side instead: the tile open path is `0x0040b850` → `0x0040b3e0` (loads the `MAPAL001` directory table `0x00179cf8`) → `0x0040a108` → `0x004192c0`, and `LEV3456R.DAT` is named in `0x0040a014` (C-4625, C-4626). Two cheap steps: (1) `callgraph.py callers g.json 0x0040b850 --depth 4` and read what the caller does with the returned handle/buffer; (2) under M9.44's virtual card, log which `(offset, length)` of a tile the file task reads first — the function that asked for the tile's first `0x1000` bytes and reads the level table at `0x2ac` is the parser's front door. A target that wraps `0x00425f40` (PO pass 18) will stop at `OSM_TaskSend`; that stop is the result, do not fake the reply.
  - Note (H101, 2026-11-17): callers measured with `tools/callgraph.py` (EU2011): `0x0041f26c` ← `0x0041e5e4`, `0x0041e64c`, `0x0041e6d0`, `0x00421548`; `0x004259bc` ← `0x0042613c` ← `0x00427144` ← `0x00427a34`; `0x00427578` ← `0x00427c4c` ← `0x00427cd4`; renderer `0x00425f40` and router `0x004266ec` each reach 48 functions with one unresolved call and import `CreateFileMappingW`/`MapViewOfFile` — the tile is memory-mapped, so the entry takes a pointer. `0x00427a34` (length `0x218`) is the common ancestor of the renderer and router readers: start there.
  - Depends: M3.5 (the three reader VAs are recorded there, done), M9.5/M9.20 (module entry + `engine_hook`, done), M9.35 (load model, done), M1.26 (the audit that found one of the three mid-function, done). M1.19 helps for `INIT` bytes; M3.6 (which sections the renderer reads, done) bounds the scope.
  - Goal: `M9.13` cannot start because `targets.json` has `tile_reader` with `reason: "no tile reader entry point has been recovered (M3)"` while the three M3.5 VAs exist — they are *reader* VAs, not a callable `(tile, dst)` entry with a known prototype. Recover the minimal entry (which VA is called with the tile buffer, its argument registers, and where it returns a verdict/level) so `M9.13` has a documented signature instead of guessing one from the format doc (rule 14).
  - Precheck: `python3 tools/pdata.py fn archive/head256.img --module Navi.exe <VA>` prints `START` for at least one M3.5 VA and `INSIDE fn 0x…` for any mid-function cite (the class this task fixes); `python3 tools/sh4xref.py --to 0x0041f26c archive/head256.img --module Navi.exe` lists callers; `grep -n 'tile_reader' tools/l3_harness/targets.json` shows the blocked entry. **Measured 2026-11-17 (PO, `fn_audit --scope docs` on `head256.img`):** only the first two M3.5 VAs are functions; the third is `INSIDE` — the correct start is the M3.5 VA minus two bytes (the corpus's `true_start`). So take starts from `pdata`, never from the format doc, and correct the M3.5 EXP in passing (H51 rule).
  - Scope: build A `Navi.exe` only — the three M3.5 VAs plus at most the two callers `sh4xref` returns; disassemble with `sh4dis.py` (LE), trace the argument setup to the buffer load (`MAP_DATA 0x00425f40` per M3.6 is the renderer consumer, not the loader). Record: real start VA, entry signature (r4..r7), the buffer/level-table global, and whether the path needs file I/O or `INIT` bytes — the latter is a `Stop`, not a blocker to record. No format claim, no new VA outside this call graph.
  - Input: `tools/sh4dis.py`, `tools/pdata.py`, `tools/sh4xref.py`, `tools/nk_decomp.py` (if a path touches sec1 `INIT`), `docs/format/map-tiles.md`, EXP-2026-11-06-M3.5-tile-reader, M9.13/M9.18 blocks, `targets.json`.
  - Hints: do not re-search by the byte grammar in `refer.md` (AGENTS: derive the signature, do not guess it). Prefer executing the candidate under `runner.py` with a module entry and a mapped factory tile — an `UnmappedAccess` at a file-I/O import is a *result* (name the import for M9.24), not a failure. Write `EU2011` next to every VA (H51). The deliverable is the signature `M9.13` copies, so keep it in `docs/format/map-tiles.md` + the EXP, not only in the log.
  - Done when: `docs/format/map-tiles.md` names one tile-reader entry VA (with build) and its r4..r7 arguments and return convention; a `runner.py` module-entry run on the factory `B28R070R.DAT` either returns a level/verdict or stops at a named import/`INIT` VA that the EXP records; `python3 tools/fn_audit.py` finds no `INSIDE` among the new VAs; `targets.json`'s `tile_reader.reason` is updated to point at `M9.13` with this entry (not "no entry recovered").
  - Stop: if all three VAs are data tables or the entry needs `INIT` bytes that M1.19 has not made ordinary, record the finding and the exact `va_class.py` verdict; do not add a target that cannot run.
  - Falsifier: the named entry does not read the passed factory tile buffer, or `pdata` shows the chosen VA is `INSIDE` another function.
  - Claims: C-4680–C-4699

- [x] **M3.28 — Who opens which file: one opener function per file family, from the name tables**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes · Pair: solo
  - Result: `docs/experiments/EXP-2026-11-19-M3.28-file-openers.md` (C-4660–C-4679); `tools/name_loaders.py` (`census`, `openers`, `--selftest`) and `tools/vcard_l3.py lookup` / `trace`. One resolver `0x0040b358(directory, name)` → file id (13 callers = the openers, table in `firmware.md` "Who names which file"); one read issuer `0x003f6c88` behind three wrappers (49 calling functions). Openers were run on the EU card: the firmware itself builds and resolves `POINT`, `ADDRE`, `FRWAY`, `INTER`, `ZCODE`, `LCTBL`, `ICADM` names. Matrix: rows 8, 9, 12, 13, 14 moved to located (opener + read issuers), `map_signals` readers 6 → 11 located, unlocated 7 → 4; rows 7 and 15 (`COORD001`, `ZIPFR001`) stay unlocated with the lookups tried. Also: 40 of the 52 file names in the firmware do not exist on the EU card; the lookup is case-sensitive; M3.11b's client is `0x003f6c88` (all reads ask for the swap). Not done: `0x003f2cc0` and `0x004125a8` did not run (state; `OSM_isSender` has no model) and are described from literals; no record parser.
  - Note (M9.44, 2026-11-19): a shortcut for the opener column: every file is addressed by `(directory id << 16) | file id` (C-4634), so the callers of the read API `0x0041841c` and the id constants they load name the reader per family without following names. `python3 tools/vcard_l3.py boot IMG256 --card-image CARD --tree` prints the ids.
  - Depends: — (H112: corrected `callgraph.py`, the name loaders of C-4625–C-4627)
  - Goal: `reader-coverage.md` has 7 rows with no located reader and 5 partial, and the number has not moved in three cycles. The firmware names every map file in a handful of functions: H112 found them in ten minutes by asking who loads each file-name string. Turn that list into the matrix's "firmware reader" column: for each of the 30 rows, the function that builds the path, the client API call it makes, and the function that receives the data.
  - Precheck: `python3 tools/sh4xref.py --image-start 0x200200 IMG256 Navi.exe --to 0x00179fa4` prints one load, `fn 0x0040a014`; `python3 tools/callgraph.py callers g.json 0x0040b358 --depth 1` lists 13 callers (rebuild `g.json` first, H112).
  - Scope: EU2011 `Navi.exe`. (1) A committed command (`tools/name_loaders.py` or a `sh4xref` mode, with `--selftest`) that lists every file-name string and name-part table in sec0 rodata with the functions that load it — expected 60 strings, 56 with a loader. (2) For each loader, its call into the client API (`0x00409ba0`, `0x00409c28`, `0x00409cc8`, `0x0040b358`) and what it does with the result — one row per file family in `docs/format/firmware.md`. (3) Update the `firmware reader` cell of every `reader-coverage.md` row this locates; `python3 tools/map_signals.py` must show the new count.
  - Input: C-4625 (the 18-row `(directory, file, CDROM.DAT)` table at `0x00179cf8`, loaded by `0x0040b3e0`), C-4626, C-4627, M3.26's role table, `tools/sh4xref.py`, `tools/callgraph.py`, `tools/sh4dis.py`.
  - Hints: names are built, not stored: `0x003fbed8`, `0x003f1640` and `0x004011a0` import `strcpy`, `strcat` and `_modls` — prefix + two digits + `.DAT`. Tile names `BxxRyyR.DAT` have no string at all (no `MAPAL001` row has a file): look in `0x0040a014`'s callees `0x00409eac`/`0x00409f60` for the hex-digit formatter, and check it against `mesh_grid.py`. The words before the table (`0x000f0004`, `0x0000f4ff`, …) and after it (`0x400`, `0x403`, `0x406`, `0x40f`) look like id maps: the row index is probably a data-kind id that the client passes in `r4`. `CMP.LST`, `COORD001.DAT`, `ZIPFR001.DAT` have no pool loader — say so in their rows (reached through `DRSTR` lookup, or not read by `Navi.exe`). Write `EU2011` beside every VA; the US build is M1.22's map.
  - Done when: the command and its selftest are in; `firmware.md` has the table; at least four `reader-coverage.md` rows move from unlocated/partial to located with a VA, each checked with `fn_audit`; rows that stay unlocated say which lookup was tried.
  - Stop: a family whose name loader only forwards a message — record the message and receiver, do not guess the reader.
  - Falsifier: a located "reader" that never reaches the client API or the map-file task in the graph.
  - Claims: C-4660–C-4679

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

- [ ] **M3.29 — Split the shared REFER candidate list per family at run time, and measure M3.23's recall**
  - Status: blocked · Owner: task/m3.29-refer-family-split · Critical: no
  - Depends: M3.23 (done), M9.38 (read watch), M3.28 (`vcard_l3.py trace`)
  - Goal: M3.23 found that `ADDRE`, `INTER`/`FRWAY`, `ZCODE` and `COORD` go through one opener `0x003fbed8` whose family is ctx +124 at run time, so a static graph gives one shared candidate list (C-3546), and its ranking misses small walkers (C-3545). A run per family with the read watch turns the shared list into per-family readers.
  - Scope: for ctx +124 = 2, 3, 4, 11 (and 1 for `POINT`) run one caller of `0x003fbed8` on the card with M9.38's read watch over the page buffer; record the functions that load record bytes per family; compare them with M3.23's QC list and the POINT/ICODE lists (recall = confirmed readers in the top 10 / confirmed readers).
  - Input: `docs/experiments/EXP-2026-11-20-M3.23-callgraph-readers.md`, `tools/callgraph.py rank`, `tools/vcard_l3.py trace`, C-4666, C-3607.
  - Done when: each of `ADDRE`, `INTER`, `FRWAY`, `ZCODE` has a list of functions that read its record bytes (or a recorded reason none was read), and the EXP gives the recall of M3.23's ranking per family.
  - Stop: if no family other than `POINT`/`LCTBL` reads its file in the run (message wait as in C-3259), record the message and stop.
  - Unblock: **M9.53** — the mount half (M9.52, answer message `0x1507`) merged as #348; **M9.53** (deliver a map request); once the mount reaches state 3 the record request `0x14b5` (`0x004066ac` → … → `0x0040a474`) issues the per-family reads, and `python3 tools/m3_29_family_readers.py run` with that request gives the `ADDRE`/`INTER`/`FRWAY`/`ZCODE` reader lists. `COORD001` stays on M3.14 (no ctx +124 value, no opener — C-5624).
  - Result: EXP-2026-11-20-M3.29-refer-family-split (blocked; Stop rule met). A boot reads `POINT001`/`ICODE001`/`ICADM001` only and ends `both tasks idle` with `0x1507` undelivered; `ADDRE`/`FRWAY`/`INTER`/`ZCODE`/`COORD` get a recorded reason (C-5620). Nine confirmed readers (`0x3eff20`, `0x3f0400`, `0x3f07f8`, `0x3f0c7c`, `0x3f17a4`, `0x3f1bb0`, `0x3f255c`, `0x3f2bc4`, `0x40a8d0`) grouped by read tag (C-5621); opener `0x003fee70` names all five families but queues no read (C-5623). M3.23 top-ten recall `2/9`; `0x003eff20` is the 11th `ICODE` candidate on the committed tree, not the 8th (C-5625, C-5626). `tools/m3_29_family_readers.py`, selftest 5/5.
  - Claims: C-5620–C-5629

- [ ] **M3.30 — Drive the REFER *search* path (not the mount path) with search type 11/12 and watch the `ZCODE` parser; probe whether anything reads `COORD001`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M3.29 (open). **Follow-on: cannot be taken until M3.29 merges `done`** — M3.30 reuses M3.29's per-family run for the search path and adds the `COORD001` probe; it is not independently takeable.
  - Goal: M3.14 (2026-11-20) found the mount state machine never reads `ZCODE0nn` or `COORD001` (no row at two positions, C-5764/C-5765), so the record walker is on the search path. Run the caller of `0x003fbed8` that issues the search (`0x003fc0ec`/`0x003fc518`, C-4666 note) with search type 11/12 on a real `ZCODE0nn`, watch the parser, and record any `COORD001` read at all.
  - Precheck: `tools/read_watch_l3.py --selftest` and `tools/vcard_l3.py --selftest` pass; `vcard_l3.py trace 0x003fbed8 --ctx 124=11` resolves `ZCODE001` (C-5764).
  - Scope: EU2011 `Navi.exe`; the search-message handler subtree of `0x003fbed8`; one `ZCODE0nn` file and `COORD001.DAT`. Excludes the mount path (already covered by M3.14).
  - Input: `docs/experiments/EXP-2026-11-20-M3.14-zcode-icode-coord.md`, C-4666, C-3546, `tools/datask_l3.py`, `tools/read_watch_l3.py`, `tools/vcard_l3.py`.
  - Done when: a function that reads `ZCODE0nn` record bytes in the search run is named with offsets/widths, or the run records why the search path reads nothing (message wait, missing model); and `COORD001` has either a reader VA or a recorded "not read by `Navi.exe` on the mount or search path".
  - Stop: if two search-message attempts return no `ZCODE` row and the read issuer does not reach a parser, write the negative with the message ids and stop.
  - Claims: C-5780–C-5789
- [x] **M3.31 — Where the firmware gets the length of a tile directory read**
  - Status: done · Owner: task/m3.31-dir-read-length · Critical: no · Pair: required
  - Depends: M3.25, M9.13 (done)
  - Goal: M9.13 observed that the data-access task reads every directory of a tile with a fixed length per level and section (`0x14100`, `0x8100`, `0x2100`, `0x6100` on three EU tiles, C-3257) and not with the directory's own size, and that a tile whose file ends before that length fails the read (C-3256). The rule is OBSERVED only. Read it from the code, so a writer can compute the length for any tile instead of copying four constants.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image <EU card> --max-reads 40 --json out.json` lists reads handled by `0x0041597c` with the four lengths above.
  - Scope: EU2011 `Navi.exe`. Find the function that fills the length word (+20) of a directory read request (callers of the read issuer `0x0040a474` in the subtree of `0x0040c308`, the section-table handler) and name its inputs: a section-table field, a level table, or constants. No writer change.
  - Input: EXP-2026-11-19-M3.25-tile-reader-entry, EXP-2026-11-20-M9.13-generated-tile-l3, `tools/datask_l3.py`, `tools/sh4dis.py`, `tools/pdata.py fn`.
  - Done when: `docs/format/map-tiles.md` states the rule with the VA that computes it, and the rule predicts the directory read lengths of a fourth tile (not `B48R058R`, `B48R068R`, `B28R070R`) before the run that measures them: `python3 tools/datask_l3.py mount … --position LAT,LON --json` on that tile prints the predicted values.
  - Stop: one session. If the length comes from a table filled by another task at run time, name the table VA and its writer and block.
  - Falsifier: the fourth tile shows a length the rule did not predict.
  - Claims: C-5820–C-5829
  - Result: EXP-2026-11-20-M3.31-dir-read-length. `fn 0x00414338` (EU2011) asks `0x100 * T[kind].n` bytes, `T` = 16 rows at `0x179c08` read by the leaf `0x0040901c(kind, 1)`, `kind` = the header level-table kind byte (merged by `0x0040aa50`, stored by `0x00409834`): `0x91` `0x14100`, `0x92` `0x8100`, `0x90` `0x2100`, `0x93` `0x6100`, `0x80` `0x1100`. 118/118 directory reads in 11 runs match; kind-byte controls give `0x3100`/`0x4100`/`0xa100`/`0x1100` and no read for a kind without a row. Fourth tile `B40R060R` (45.46 N 9.19 E): 5/5 reads as predicted before the run. New `tools/dir_read_len.py` (`table`, `predict`: length per level and directories read past EOF — 53 factory section-4 directories in 35 of 46 files); `datask_l3.py` prints the lookup per read. `B60R048R` mounts only its header (C-5825) → new **M3.33**. C-5820–C-5826.
- [x] **M3.34 — Firmware reader of the POINT spatial tree and the code that turns (copy A, fine) into map units**
  - Status: done · Owner: task/m3.34-poi-position-reader · Critical: yes · Pair: solo
  - Depends: M4.27 (done), M4.52 (POINT header parser and page loader located, done)
  - Goal: M4.27 read the POI position from the file structure and fitted it to 16 reference points (C-2679): `u = (v & ~15) + 4·(v & 3) + fine/512`, origin 52736. Rule 13 wants the firmware's own arithmetic: find the code that takes a name record's copy A and bytes 6–9 (or a spatial-tree leaf) and produces a map coordinate, and the reader of the spatial tree (cell `0x85a`, 16-byte entries `0008 …`), so the formula, the two marker bits and the leaf flag bits stop being a fit.
  - Precheck: `python3 tools/point_census.py --selftest` passes; `tools/point_locator_l3.py` runs the header parser `fn 0x003f930c` (EU2011) on a card.
  - Scope: EU2011 `Navi.exe` (name the US2011 twin if cheap). Start from the header parser's object (cell `0x85a` lands next to cell `0x82a` at `+24`), the constants `0x7ff`, `0x1ff`/`>> 9`, `52736`, and callers of the name accessor `0x003f632c`. L3 run on a factory page: feed one name record, read back the coordinate, compare with `point_census.fine_position`.
  - Input: EXP-2026-11-20-M4.27-point-census-fine-position, `docs/format/refer.md` "Fine POI position", EXP-2026-11-20 M4.52 (`point_locator_l3.py`), `tools/callgraph.py`.
  - Done when: the conversion routine is named with its VA and its arithmetic written out, and an L3 run on ≥ 100 factory name records agrees with `fine_position` (or the EXP states the exact difference and `point_census.py` is corrected); the spatial-tree reader is named or the EXP says which message handler receives the tree bytes.
  - Stop: one session; if the conversion happens in another task's handler that the harness cannot reach, name the handler and block.
  - Claims: C-6540–C-6549
  - Result: `docs/experiments/EXP-2026-11-21-M3.34-poi-position-firmware.md` (C-6540–C-6546). Conversion found and run: EU2011 `fn 0x003c032c` builds a mesh point (`id = bytes 2–5 & 0xfff3fff3`, `x`/`y` = words 6/8 `& 0x7ff`) and `STDDLL!STD_MeshPnt_chgMapPnt` gives 1/512″ units (mesh = 1/48° × 1/32°, 2048 steps). New `tools/poi_position_l3.py` (`--selftest`) runs both from the image: 15,469/15,469 records of `POINT010` and 9,483/9,483 of all 33 EU files equal `fine_position` within 1 unit (6 cm); controls 0 matches. New `tools/sh4fpu.py` (FPU for PySh4). `point_census.fine_fields` masks both fine words. **Negative part:** the spatial-tree reader was not found in one session → M3.35.
- [x] **M3.35 — Firmware reader of the POINT spatial tree (cell `0x85a`)**
  - Status: done · Owner: task/m3.35-point-spatial-tree-reader · Critical: no · Pair: solo
  - Depends: M3.34 (done)
  - Goal: M3.34 tied the POI position to firmware code but did not find the code that reads the spatial tree (16-byte entries `0008, u32 ptr, u16 size_w, u16 kx, u16 ky, u32 fine`, node end `0005 ffffffff u32`, C-2678). Name it (EU2011), or name the message handler that receives the tree bytes, so M5.63 knows which leaf fields the unit really reads when a POI is moved or added.
  - Precheck: `python3 tools/poi_position_l3.py --selftest` passes; C-6546 lists what M3.34 ruled out.
  - Scope: EU2011 `Navi.exe`, static + L3. Leads: the seven callers of `fn 0x003c032c` (`0x003b1b44`, `0x003b42c0`, `0x003b4b58`, `0x003b5024`, `0x003b5808`, `0x003c0bf4`, `0x003d0110`); callers of the generic walker `fn 0x003f5194` on class-0 records (entry lengths 8 and 5 words fit its framing); the header parser's object field for cell `0x85a` (next to `+24`, `fn 0x003f930c`); `tools/datask_l3.py` read-completion handlers (M3.25).
  - Input: EXP-2026-11-21-M3.34-poi-position-firmware, EXP-2026-11-20-M4.27-point-census-fine-position, `docs/format/refer.md` "Fine POI position".
  - Done when: a function that reads `kx`/`ky`/`fine` of a tree entry is named with its VA and run in L3 on one factory node (descent to a leaf whose ordinal equals the `point_census` one), or a negative EXP lists the handlers checked.
  - Stop: one session.
  - Claims: C-6830–C-6839
  - Result: the tree is read by the nearest-POI search of EU2011 `Navi.exe`: child loader `fn 0x0040f944`, step `fn 0x004110dc`, node walker `fn 0x004114dc`, distance `fn 0x00408ea4`. New `tools/point_tree_l3.py` runs them on factory trees: 5 files, 237/237 trees ACCEPT, 8,475/8,475 cells return the ordinals `point_census` reads (16,616 leaves), controls moved/cut/flag 237/237, code 33/33. A leaf needs flag `0x0800`, code 63 (or 0), ordinal, two 11-bit fine values and a `0005` terminator; leaves with other codes are skipped unless `*0x005638ec` holds the code. EXP-2026-11-21-M3.35-point-spatial-tree-reader, C-6830–C-6839; follow-up M3.37

- [ ] **M3.37 — POI search set-up: upper-level drivers, the leaf code and `*0x005638ec` (EU2011, then US2011)**
  - Status: blocked · Owner: — · Critical: no · Pair: solo
  - Depends: M3.35 (done)
  - Goal: M3.35 runs the child loader, step, node walker and distance function of the nearest-POI search on factory trees, with the search state written by the tool. Three things are not known: who writes that state (root loader `fn 0x0040f674`, drivers `fn 0x00411fd4`/`fn 0x0041235c`, caller `0x003f383c`), what the leaf's 6-bit code means (a leaf with a code other than 0/63 is kept only when `*0x005638ec` holds it, C-6836), and whether the category filter (`0x00d5d7dc`) reads a field a writer must set.
  - Precheck: `python3 tools/point_tree_l3.py --selftest` prints `selftest OK (14 checks)`.
  - Scope: EU2011 static + L3 with `tools/point_tree_l3.py`. (1) writers of `*0x005638ec`, `*0x0056389c`, `*0x00d5d7e4` (`sh4xref.py --to`) and what value sets them (language? brand?); (2) census of leaf codes per file and category with `point_census.py`, and what differs between the name records of leaves that share a position but not a code; (3) run `fn 0x0040f674` and one upper-level driver so the tool no longer writes tree base and levels by hand; (4) the category filter on one tree with a category level; (5) locate the US2011 twins of the four functions by byte pattern.
  - Input: EXP-2026-11-21-M3.35-point-spatial-tree-reader (C-6830–C-6839), `tools/point_tree_l3.py`, `tools/point_census.py`, `docs/format/refer.md`.
  - Done when: the writer of `*0x005638ec` is named and the code's meaning is supported by a census (or stays HYPOTHESIS with the counter-examples listed), the root loader runs in L3 on one tree, and the US2011 VAs are listed or reported missing. EXP + claims; `docs/format/refer.md`.
  - Stop: one session.
  - Falsifier: no code writes `*0x005638ec` (then coded leaves are dead data for this build).
  - Claims: C-6860–C-6869
  - Blocker: root loader fn 0x0040f674 executes in L3 and sets *0x00d5b858 on POINT010 tree 0, but full root descent/upper driver L3 needs seeded request state (UnmappedAccess on STEP from minimal ctx); leaf-code meaning remains HYPOTHESIS
  - Unblock: M3.38
  - Result: EXP-2026-11-22-M3.37-poi-search-setup; C-6970-C-6979; writer fn 0x003f2f98 named, census {63:2631890,6:3414,4:3356,5:3064,10:3061,7:2866,2:2803,8:2761} 4945 same-pos multi-code, US twins listed, root-load sets base block 0xd77 but step BLOCKED

- [ ] **M3.38 — Seeded search request for the POI tree: run the root loader and an upper-level driver through a real tree in L3 (EU2011)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M3.37
  - Goal: M3.37 ran the root loader `fn 0x0040f674` on POINT010 tree 0 (it sets `*0x00d5b858`), but the root descent and the upper-level driver stop with UnmappedAccess on STEP, because the tool starts them from a minimal context instead of the request object the firmware builds. Seed that object so the whole nearest-POI search runs from the root without hand-written tree base and levels.
  - Precheck: `python3 tools/point_tree_l3.py --selftest` passes; the M3.37 run of `ROOT_LOAD` sets base block `0xd77` and then STEP is BLOCKED (EXP-2026-11-22-M3.37-poi-search-setup).
  - Scope: EU2011 static + L3 with `tools/point_tree_l3.py`. (1) Read the request builders `fn 0x003f4658` and `fn 0x003f4948` and list the fields they write; (2) add a seeded request object to `point_tree_l3.py` with those fields; (3) run `ROOT_LOAD` and `DRIVER_A` (`fn 0x00411fd4`) on POINT010 tree 0 until the first leaf is returned; (4) trace callers of the `*0x005638ec` writer `fn 0x003f2f98` to name the UI or search mode that sets the leaf code.
  - Input: EXP-2026-11-22-M3.37-poi-search-setup (C-6970–C-6979), EXP-2026-11-21-M3.35-point-spatial-tree-reader, `tools/point_tree_l3.py`.
  - Done when: one search from the root returns a leaf in L3 with the seeded request (no hand-written base/levels), or the missing field is named; the mode that sets `*0x005638ec` is named or reported unknown. EXP + claims.
  - Stop: one session.
  - Falsifier: with every field the builders write seeded, STEP still faults at the same address.
  - Claims: C-8190–C-8199

- [x] **M5.62 — `l2check`: refuse a generated tile that lists fewer than three sections**
  - Status: done · Owner: task/m5.62-l2-tile-section-list · Critical: no · Pair: solo
  - Step: P1
  - Depends: M3.33 (done)
  - Goal: the firmware leaves a `BxxRyyyR.DAT` whose section list at header `0x800` has fewer than three entries on the first mount and goes on in the first tile of its box table (C-6080–C-6083). Nothing in L2 says so: a writer change that drops an empty section would pass every gate and lose the tile on the unit.
  - Precheck: `python3 tools/tile_drop_l3.py --selftest` passes; `python3 tools/l2check.py --help` lists the tile checks.
  - Scope: one rule in `tools/l2check.py` (and its selftest) for generated `BxxRyyyR.DAT` tiles: three entries at `0x800`, `0x806`, `0x80c`, none `ff ff ff ff`. Factory tiles copied verbatim are reported as INFO, not failed (8 of 45 factory tiles have fewer, C-6085). Use `tile_drop_l3.parse_section_list`.
  - Done when: `l2check` fails a synthetic tile whose third entry is blanked and passes the unchanged `one_tile_pipeline.py --synthetic` tile; the selftest holds both cases.
  - Stop: one session.
  - Claims: C-6510–C-6519
  - Result: `docs/experiments/EXP-2026-11-21-M5.62-l2-tile-sections.md` (C-6510–C-6519). `tools/l2check.py` gains `tile_section_list` (via `tile_drop_l3.parse_section_list`): a `BxxRyyyR.DAT` named on `--tiles`/`--semantic-tiles`/`--class-tiles` must list three entries at `0x800`/`0x806`/`0x80c`, none `ff ff ff ff`; `LEV3456R.DAT` is out of scope. The unchanged `one_tile_pipeline.py --synthetic` `B48R058R` tile passes (`[tile_section_list] OK (B48R058R.DAT=3; …)`, exit 0), the same tile with `0x80c` blanked fails naming `0x80c` (exit 1); a tile identical to the new `--factory-root` file (factory verbatim) and an unnamed default-list tile are INFO, so the raw EU 2011 factory card stays `RESULT: PASS` (the 2/2/1-entry B28R070R/B30R060R/B58R070R are INFO, C-6085). `--selftest` holds all five cases (27 ok); `selftest.py --only l2check` passed=1; gate 4 pass, 0 fail, 0 skip. Claim block C-6510–C-6519 (C-6500–C-6509 is reserved by M4.58).

- [ ] **M3.32 — Who reads the bytes inside an `ADDRE` record's point block and house-range items**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M3.13 (done)
  - Goal: M3.13 located the record reader and the leaves that return block 1 (`rec+4`, `rec[2]` words: coordinate id + point tokens `TT 40 XX YY`) and range item `i` (`fn 0x003f5624`), but not the code that reads the bytes inside them (C-5938). Run the callers and name the instructions that read the coordinate id, a point token and a range item's `subtype`/`:N:;:M:` text, so the writer (M5.18) knows which of those bytes the firmware uses.
  - Precheck: `python3 tools/addre_field_reader.py run archive/head256.img --cmp <EU ADDRE001.DAT.cmp> --build eu2011` passes (the bound context), and `python3 tools/sh4xref.py archive/head256.img Navi.exe --to 0x003f5624` lists `fn 0x003ad680`, `fn 0x003ad9a4`, `fn 0x003b9d38`, `fn 0x003bacc4`.
  - Scope: EU2011 `Navi.exe`, the four callers above and their callees (`fn 0x003ad440`, the `0x003c5bxx` setters); one bound `ADDRE001` block, read watch on the page. Out of scope: the directory/cells/index search path (M3.30).
  - Input: EXP-2026-11-20-M3.13-addre-reader-l3, `tools/addre_field_reader.py` (`build_context`), `tools/l3_harness/engine.py` read watch, `tools/sh4dis.py`.
  - Done when: an EXP lists, for record 0 of ADDRE001 block 0, every instruction that reads a byte of block 1 or of a range item, with the byte offset and what it computes; `docs/format/refer.md` field table updated; or a blocked EXP naming the input the callers need.
  - Stop: one session; if a caller needs a context object nothing builds, name it and block.
  - Falsifier: a caller that reads none of these bytes when given a record with points and ranges.
  - Claims: C-6040–C-6049

- [ ] **M3.36 — Board truth for the blocked REFER/ADDRE chain: re-open or re-word M3.29, M3.30 and M4.23 (the tasks M3.13/14/16/49 actually wait on)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (board audit, one session; it unblocks M3.13, M3.14, M3.16 and M4.49 indirectly by making their `Unblock` truthful, and is the fix half of H125's checker)
  - Goal: four tasks wait on three records that are not what their `Unblock` says. M3.29 is `blocked` with `Unblock: M9.53`, and **M9.53 is `done`** — has been since 2026-11-20 16:54Z — yet nobody re-opened M3.29 (rule 15). M3.13/M3.14/M3.16 are `blocked` on M3.30, and M3.30 is `open · Owner: —` with a `Depends` line that says it "cannot be taken until M3.29 merges `done`": an open door onto a locked task, so the picker sees a free task that is not takeable and misses the real one. M4.23's `Unblock` names M4.25 and M4.26, both archived `[x]` on 2026-11-09 (`docs/research/todo-history-2026-11-09.md`), so the trigger it waits for is a merge that cannot happen. This is not a claim defect (a rule-17 record fix), it is the pick path: a newcomer reading `M3.30` finds no reason it is stuck.
  - Precheck: for each pair, the two status lines print what this Goal quotes: `python3 tools/board.py show M3.29 | grep -m1 Status:` → `blocked`, `python3 tools/board.py show M9.53 | grep -m1 Status:` → `done`; `python3 tools/board.py show M3.30 | grep -m1 Status:` → `open`, its `Depends:` line names M3.29; `grep -n 'M4.25\|M4.26' docs/research/todo-history-2026-11-09.md | grep -c '\[x\]'` is non-zero. Re-run each `Done when` of M3.29/M3.30 only far enough to state *why* it is blocked (its own Result already does for M3.29).
  - Scope: **TODO.md task blocks only, and only these four** (M3.29, M3.30, M4.23, plus the `Unblock` line of each of M3.13/M3.14/M3.16/M4.49 if the target moves), edited through `python3 tools/board.py field`/`status`/`block` — never by hand. Two allowed outcomes per task, chosen by what its Result/Stop says, not by optimism: re-open (M3.29 if M9.53 is enough, rule 15) or re-word (say exactly which part is missing and which *live* task provides it; for M4.23 that means a new or existing task that re-tests the regulation word now that M4.25's audit is archived, not the archived ID). If a task needs new work to become takeable, add that as a new task with its own ID and point `Unblock:` at **it**. No `Done when`/Goal/Scope rewrite beyond the status/`Unblock`/`Depends` truth; no claim rows.
  - Input: `tools/board.py` (`field`, `status`, `block`, `show`), the M3.29/M3.30/M3.13/M3.14/M3.16/M4.23/M4.49/M4.25/M4.26/M9.53 blocks, `docs/research/todo-history-2026-11-09.md`, EXP-2026-11-20-M3.29-refer-family-split, EXP-2026-11-20-M9.53-record-block-read.
  - Done when: on the merged board, a script over `TODO.md` finds **0** `blocked` tasks whose `Unblock` names a `done` ID and **0** `open` tasks whose `Depends`/`Unblock` says "cannot be taken" while naming an ID that is also `open` — specifically M3.29 is `open` (and names its one missing piece) or its `Unblock` names a task that is not `done`, M3.30 is `blocked` on that same piece (or takeable with its `Depends` corrected), and M4.23's `Unblock` names a live task not an archived one. `python3 tools/board.py lost --base origin/main` exits 0 (status edits move no ID); `python3 tools/todo_check.py` is no worse than before the pass; the count of the class before and after is quoted from one command.
  - Stop: one session. If making a task takeable needs a `Done when` change, stop at the status/`Unblock` truth and file the re-scope as a new task; never rewrite a `Done when` in an audit.
  - Falsifier: a `blocked` task left in the class after the merge (H125's checker still names it), or a status flip that `board.py` reports as lost IDs — the edit target is wrong, revert it with `git checkout -- TODO.md` and redo through the tool.
  - Claims: C-6640–C-6649

- [ ] **M3.42 — `MDP_*RcvParcel`: the parcel receive queue in the firmware — who fills it and what a 'parcel' is there**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: The ROM names functions `MDP_pushRcvParcel`, `MDP_popRcvParcel`, `MDP_freeRcvParcel` in error strings. A queue of received parcels sits between the file reader and the consumers; its element structure is the firmware's own definition of a parcel (id, level, buffer, length), and the map client found in M3.25/M3.28 should be its producer.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --image-start 0x200200 MDP_pushRcvParcel` prints the module and string VA; `python3 tools/reader_precheck.py --help` works.
  - Scope: EU2011 (US2011 by `tools/fn_match.py`): the three functions (pdata START), the element layout, producers and consumers one level up, and how it relates to the read-completion handlers of `tools/datask_l3.py`.
  - Input: `tools/sh4xref.py`, `tools/callgraph.py`, `tools/datask_l3.py`, EXP-2026-11-19-M3.25-tile-reader-entry.
  - Done when: an EXP with the queue element table (offset, size, meaning, evidence) and the producer/consumer list; `docs/format/map-tiles.md` gains a 'what the firmware calls a parcel' paragraph; signature source stated (error string → xref — strong).
  - Stop: one session; if the strings are referenced by a logging helper only, name the helper's callers and stop after one hop.
  - Falsifier: the queue carries messages of another subsystem (traffic or telematics 'parcels').
  - Claims: C-7780–C-7789

- [ ] **M3.39 — The order in which the firmware reads a tile, compared with `kiwiread`'s parse order**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: M3.42
  - Goal: If our tile is KIWI main-map data, the firmware should walk it in the specification's order: management header, then road, background and name frames by their offsets. The read-watch tools can print the firmware's order; compare.
  - Precheck: `python3 tools/read_watch_l3.py --help` works and `python3 tools/datask_l3.py mount --help` runs the map client.
  - Scope: EU2011, one level-1 tile: sequence of first-touch offsets grouped by our section/directory names; the same tile's structure as M4.66–M4.71 name it.
  - Input: `tools/read_watch_l3.py`, `tools/datask_l3.py`, `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`).
  - Done when: an EXP with the ordered list (offset range → structure → reading `fn`) and a three-way verdict per frame (same order / different / not read at mount).
  - Stop: one session.
  - Falsifier: the firmware reads the sections in an order that depends on the request kind only (no fixed parse order).
  - Claims: C-7790–C-7799

- [ ] **M3.40 — Who opens `REFER002`: the EV-layer opener and its read path**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: Matrix row 24 has no reader. Before decoding (M4.85) or writing (M5.79) the EV layer, locate what opens its files and whether the reads go through the same search-type opener as `REFER001`.
  - Precheck: `python3 tools/reader_precheck.py --help` works; `python3 tools/ce_strfind.py archive/head256.img --image-start 0x200200 --encoding all REFER002` prints the name string(s) in executable-reachable data.
  - Scope: EU2011 (US2011 by `tools/fn_match.py`): string xrefs → opener (pdata START) → read issuers; signature source: the file-name string (strong). Corpus: `Navi.exe` and its `Navi*` DLLs, counted.
  - Input: `tools/sh4xref.py`, `tools/callgraph.py`, `tools/datask_l3.py`, `tools/m3_29_family_readers.py`, `docs/format/refer.md`.
  - Done when: the opener VA and read issuers are in `docs/format/refer.md` and matrix row 24 (`located`), with the L3 command that runs the opener on the card and the files it requests; EXP + claims; `tools/gate.py` passes (fn_audit).
  - Stop: after three xref patterns with no opener, set blocked with the patterns tried (rule 14).
  - Falsifier: the name string has no code reference in any module (opened through a table: then name the table).
  - Claims: C-8150–C-8159

- [ ] **M3.41 — Which code draws background polygons: the renderer's reader of the odd-partner record**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: The road path of the renderer is known (`LOC_map` walk, M9.58/M9.67). The background path (water, forest) is not, and a background writer (M5.74) needs its acceptance rules.
  - Precheck: `python3 tools/read_watch_l3.py --help` works; the M9.58 EXP names the renderer entry that walks a record.
  - Scope: EU2011: run the renderer walk on a tile with background data under a read-watch limited to the odd-partner record; list the reading functions (pdata START); signature source: L3 read-watch (strong).
  - Input: `tools/read_watch_l3.py`, `tools/locmap_l3.py`, `tools/datask_l3.py`, the M9.58 and M9.67 EXPs.
  - Done when: an EXP with the reader function(s), the fields they read in order, and a `tools/l3check.py` target (or recipe) that runs them on a factory tile; matrix row 17 notes it.
  - Stop: if nothing reads the record on the mount/draw path available at L3, record the path tried and set blocked on M8.H10 (the L4 read-watch).
  - Falsifier: the odd-partner record is read by the same function as the road record with a type switch (then there is no separate reader — say so).
  - Claims: C-8160–C-8169

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
  - Step: P3
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
  - Step: P2
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
  - Status: open · Owner: task/m4.8b-coord-py-real-pois · Critical: yes
  - Step: P4
  - Blocker: bit-packed POINT pages (`POINT002/008/029`, 5405 pages) remain
    undecoded; no 0..2047-class geographic sub-unit position field linkable to
    the 16 M4.8b reference POIs was found by structural probe
    (`poi_bitpack_probe`, raw-A pair 0/1796 in P01 shard), so local scale 1 vs 2
    is untestable and the "within a few metres"/local-scale done-when is unmet.
    Latitude-offset "other method" is a non-pinnable fit to Wikipedia centroids.
    Origin 52742 (longitude) remains supported (C-1902).
  - Unblock: re-opened 2026-11-20 by M4.27 (C-2679, EXP-2026-11-20-M4.27-point-census-fine-position): the name record holds the fine position (`rec[6..9]`, 512 steps per packed unit inside a 4-unit sub-cell of copy A; `tools/point_census.py refs`, median 115 m on the 16 references, 3 within 15 m). What is left for this task: `coord.py` for point ids (M4.61) and ≥ 10 POIs with a building-level reference, so the "within a few metres" done-when can be judged. The earlier note (M4.37: format carries no sub-unit coordinate) is corrected.
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

- [x] **M4.16 — Place `RDSTM001` rows on the map**
  - Status: done · Owner: task/m4.16-rdstm-place · Critical: yes · Pair: solo
  - Result: EXP-2026-11-20-M4.16-rdstm-place-closure — done-when met on the EU 2011 card: join key = TMC location code; `rdstm_place.py place-all` carries 110,788/110,795 joined records of all 14 RDSTM tables to a level-2 (tile, parcel, node, link) with coordinates, positive neighbour < 1 km 94,551/95,176 vs shuffled 129 (reproduces C-5400/C-5401 exactly); 20 CZ D5 junctions listed with tile `B48R058R.DAT` and coordinates (Stříbro, Plzeň-západ, Rokycany at their known positions). C-5950–C-5951; C-1812 superseded. M4.16c and M4.2 no longer wait on this block. Data-side only: the firmware reader is M4.49.
  - Done when: ≥ 20 rows are matched to tile road segments with coordinates, with the join key named and a random-key control showing ~0 matches (original wording, restored at close).
  - Re-opened (rule 15, PO 2026-11-20): `Unblock` M4.16b is done and it found the join the blocker lacked: location code → `(group, entry)` → level-2 node (M4.16e, M4.16b second EXP, C-5400–C-5403; table codes M4.16d, C-2320–C-2323). This task is now a closure: re-run its own `Done when` with `python3 tools/rdstm_place.py place-all`, record the numbers, and close it or name what is still missing. Then check `M4.2` and `M4.16c`, which wait on this block.
  - Step: P3
  - Depends: M4.15 (M4.8 helps)
  - Goal: a row → tile/mesh → coordinate link, which M4.2, M4.3 and M5.3 need.
  - Input: `ref`/`src`/`dst` values (M4.1), tile road records
    (`tools_ze0`, `harness.py`), `COORD001` mesh formula, `mesh_grid.py`.
  - Unblock: M4.16b (per-record field directory), or M4.16c (the `INTER`/`FRWAY`
    `ref` lead) if the directory does not resolve the join.
  - Blocker (history, resolved by M4.16b/M4.16e): M4.1 16-byte fields (`ref/src/dst/code`) give no segment-specific
    join (hits at chance vs dense lid space; `ref`∩parcel/AB=0; C-1810) and
    M4.15/M3.7 leave framing/TMC semantics undecoded. `INTER*` `ref` byte-pattern
    enrichment (real>>random) is an unverified lead (C-1811).
  - Result (history, superseded): EXP-2026-11-06-M4.16-rdstm-placement; `tools/rdstm_place.py` probe
    + selftest. Join key NOT identified; done-when not met (negative).
  - Claims: C-5950–C-5959 (was C-1810–C-1819; fresh block for this run)

- [x] **M4.16b — Decode RDSTM per-record field directory (C-884) and re-test placement**
  - Status: done · Owner: task/m4.16b-rdstm-field-dir-placement · Critical: yes
  - Result: EXP-2026-11-20-M4.16b-tmc-placement-all-tables — with the M4.16e link-group rule, `rdstm_place.py place-all` carries 110,788/110,795 location-code-joined TMC records of all 14 RDSTM tables (14 countries) to level-2 node coordinates: 110,788/110,788 in the table's country (random refs 2,048/27,998), 94,551/95,176 < 1 km from the TMC positive neighbour (shuffled 129); 60,321 also resolve through set 0 (level 4) and all lie < 5 km from their level-2 nodes (shuffled 256). Join key = location code (neg/pos agreement is a confirmation). Roles `k&3`: role 1 = reversed role 0 in 24,948/66,443 (HYPOTHESIS, to M4.49); flag bits not decoded. C-5400–C-5403.
  - Reopen note (M4.16e, 2026-11-20, rule 15): the link groups are decoded (EXP-2026-11-20-M4.16e-rdstm-link-groups); `python3 tools/rdstm_links.py place LCTBL001.DAT RDSTM001.DAT MAPAL001 --table-pair 0` maps 8,532 CZ records to level-2 node coordinates with controls, so the done-when can now be closed (blocker below kept as history).
  - Blocker (2026-11-19, resolved by M4.16e): field directory decoded and verified (EU 247,089 / US 303,023 records exact) and the records join `RDSTM001.DAT` by TMC location code (167,204/172,752, controls 0), but the `RDSTM001` link references (`group 0..3131`, `index`) are not decoded to MAPAL mesh/parcel/link, so no record reaches tile/mesh/coordinates.
  - Unblock: M4.16e (decode the RDSTM001 link groups after `0xccce00`). The `0x00d53500` table is a handle cache, not a schema (C-5130): M3.22 is no longer this task's unblocker.
  - Result: EXP-2026-11-19-M4.16b-tmc-field-directory (directory rule from `0x003f56bc/0x003f5d98/0x003f5e10`; `tools/tmc_fielddir.py`; `rdstm_place.py probe-decoded` negative). C-5130–C-5136.
  - Blocker (history, negative EXP kept): **impossible with current inputs / blocked by compressed `.data` (Navi.exe sec1)**. Precheck: `sh4dis Navi.exe --image-start 0x200200 --check-real` OK on IMG256 `92aa525d…` (M1.11c RDSTM pins, no `.word` gap at named walk sites; MOVT/SHAR/SHLD/SHAD done). `cerom va2file 0x00d53500` → unmapped (`0x-8bb8d900`); `0x00d53500` (schema descriptor consulted by `0x003f51e0`, `[0x003f52b8]=0x00d53500`) lies in **Navi.exe sec1 `va 0x55d000 vsize 0xff16ae psize 0x457c flags 0xc8002040 COMPRESSED rw-`** (covers `0x55d000–0x154e6ae`), so schema bytes/field lengths are unreadable with current inputs. C-884 walk not reproduced to true per-record boundaries; `rdstm_place.py` not re-run on decoded fields; no ≥20 decoded-record mapping, no named join key, no ~0 random-key control. Done-when **not met**. Join/placement route remains **M4.16d** (once true decoded TMC fields exist).
  - Note (M3.22 done, 2026-11-19, rule 15): `0x00d53500` holds 4-byte page **pointers** written by the task-message writers, not an on-disk field directory (EXP-2026-11-19-M3.22-d53500-writer-l3, C-5127); the RDSTM schema must come from the page bytes the pointers name.
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker VA `0x00d53500` = BSS sec1 +0x7f6500 (zero at load; find writer/runtime init, not M1.2f). Boundary VAs explicit: `0x0055d000` = IAT `COREDLL!Sleep` (sec1 start mention), `0x00ff16ae` = BSS (range end mention). Rerun via M3.22 (writer) + M9.35 context; do not claim M1.2f unless an INIT VA is identified.
  - Unblock (superseded 2026-11-19 by C-5130, kept as history): (H49) **M3.22** — `0x00d53500` is BSS (C-3442), decompressed sec1 is zero there; the schema is written at run time. Old wording: `M1.2f` and/or `M8.E1/M1.2g/M9` verified path yielding **Navi.exe sec1 decompressed bytes** for build A (so `0x00d53500` schema contents are readable). M1.11c walk opcodes are done and **not** an unblocker.
  - Re-opened (PO grooming 2026-11-09, rule 15): M1.11c merged; decoder-gap blocker no longer holds. Re-blocked on schema bytes in compressed sec1 (this task).
  - Result (negative, prior): EXP-2026-11-08-M4.16b-record-framing — gate passed (five functions plain in Navi.exe sec0; callees verified); walk not run; done-when not met.
  - Result: EXP-2026-11-08-M4.16b-rdstm-field-walk (negative/blocked: schema `0x00d53500` in Navi.exe sec1 COMPRESSED `rw-`, unreadable; walk/boundaries/placement not reproduced with current inputs). C-2300–C-2309.
  - Depends: M4.15
  - Precheck: `python3 tools/sh4dis.py IMG256 Navi.exe --image-start 0x200200 --check-real` (M1.11c pinned window) confirms no `.word` gap at M4.16b walk sites; `python3 tools/cerom.py --image-start 0x200200 IMG256 va2file 0x00d53500` resolves schema-table location (or records it as compressed `.data`).
  - Goal: reproduce the per-record length/offset directory walk from bytes to recover true TMC field boundaries, then re-run `tools/rdstm_place.py` on decoded fields (location/area/front/rear/inter-section).
  - Scope: the C-884 directory walk (`0x003f56bc`, `0x003f5e10`, schema `0x00d53500`) on Navi.exe build A; ≥20 decoded records tested for placement. No RDSTM writer.
  - Done when: ≥20 decoded records map to tile/mesh/coordinates with a named join key and ~0 random-key control, or the mapping is proven impossible with method recorded.
  - Stop: if schema table `0x00d53500` is unreadable (compressed `.data`) or the walk cannot be reproduced with current inputs, set `blocked` naming that dependency and keep the negative result.
  - Claims: C-5130–C-5136, C-5400–C-5403 (second pass; block C-5400–C-5409, C-5404–C-5409 spare) (reserved block C-5130–C-5139, C-5137–C-5139 given to M4.16e; was C-2300–C-2309 (was C-1840–C-1849, a collision with M5.1b))

- [x] **M4.16e — Decode the `RDSTM001.DAT` link groups to MAPAL mesh/parcel/link**
  - Status: done · Owner: task/m4.16e-rdstm-link-groups · Critical: yes
  - Result: EXP-2026-11-20-M4.16e-rdstm-link-groups — the `0x1000` header lists two sets of 14 tables and one group index per set (`0xcda000`, `0xe78500`); ref `(group, entry)` → 4-byte entry `(node, link)` of the section-2 record of a level-4 (set 0) / level-2 (set 1) parcel named in the group (1,877,054/1,877,891 and 417,540/422,683 fit, random node 5.7 %/0.4 %); every joined TMC record of the CZ (8,532) and DE (22,884) tables lands on a node in its own country (random refs 5 %/19 %) and next to its TMC neighbour (< 1 km 99.9 %, shuffled 0.1 %). `tools/rdstm_links.py`. Firmware reader not located: M4.49. C-5137–C-5139, C-5370–C-5372.
  - Depends: M4.16b (record directory + location-code join, done as far as the link refs)
  - Goal: turn an `RDSTM001` link reference (`u32`: `>>16` = group 0..3131, `&0xffff` = entry) into a MAPAL mesh/parcel/link, so ≥20 TMC records map to coordinates (the M4.16b done-when).
  - Input: EXP-2026-11-19-M4.16b-tmc-field-directory (C-5134–C-5136); `tools/tmc_fielddir.py join` (codes → refs); EU `RDSTM001.DAT` `f822044c…` region `0xccce00..EOF` (≈2,790 0x100-aligned blocks of 4-byte entries with `0x40/0x60/0x80/0xa0/0xc0/0xe0` tags; 2,294,877 indexed entries in 3,132 groups); the `0x1000` header (`0x180` words) of `RDSTM001.DAT`; `clarion_rd.py` (sec2 parcel code, 13-bit link ids).
  - Precheck: `python3 tools/tmc_fielddir.py join LCTBL001.DAT RDSTM001.DAT --min-records 100` → `total neg/pos agree 167204/172752`, controls 0 (the refs exist and are keyed).
  - Scope: EU 2011 card only; groups → blocks, entry format, group → mesh; no writer.
  - Done when: ≥20 TMC records (code, name) map through their refs to MAPAL tile/parcel/link coordinates, with a random-key control near 0 and a named mapping rule; or the mapping is shown not to exist with method recorded.
  - Stop: if the group directory cannot be found from the file header or block order, look for the firmware reader of these blocks (search the readers of `RDSTM001` by reachability, M3.23) and report `blocked` with the block census.
  - Claims: C-5137–C-5139 (block from M4.16b's reserve), C-5370–C-5372 (C-5373–C-5374 spare, C-5375–C-5379 given to M4.49)

- [ ] **M4.49 — Locate the firmware reader of the `RDSTM001.DAT` link groups and run it in L3**
  - Status: blocked · Owner: task/m4.49-rdstm-group-reader · Critical: no
  - Step: P3
  - Blocker: no function of the TMC data-layer subtree of `Navi.exe` (EU2011, 230 functions from the `0x14e4`/`0x14f4` message handlers and the TMC search senders, depth 8) shows the derived link-group signature (`and 0x1fff` 0 hits; no function with two of `0x1fff` mask / address build / 6-byte stride / 18-byte head); the module's three mask+address-build functions are guidance code. Lead: message `0x14f4` shares the TMC handler `0x004003f4` with `0x14e4` and has its own buffer in the generic sector reader `0x00417618` (EU2011).
  - Unblock: M4.51 (senders of `0x14f4`/`0x14e4` and the file/offset a `0x14f4` request reads).
  - Note (M4.51 blocked, 2026-11-20): no static sender of `0x14f4` (EXP-2026-11-20-M4.51-tmc-14f4-senders); the next unblocker is M4.53 (L3) or M8.E4.
  - Note (M4.53 done, 2026-11-20, rule 15): in L3 a `0x14f4` request reads `REFER001` POINT/ADDRE/INTER files by its sub word, never `RDSTM001.DAT` (EXP-2026-11-20-M4.53-tmc-14f4-l3, C-5680–C-5682); the `0x14f4` lead is refuted, so this task stays blocked with M8.E4 (read watch on `RDSTM001.DAT` `0xcda000`/`0xe78500`) as the unblocker.
  - Result: EXP-2026-11-20-M4.49-rdstm-group-reader (negative with controls; `tools/rdstm_reader_scan.py`). C-5375–C-5379.
  - Depends: M4.16e
  - Goal: rule 13 for the M4.16e decode: find the `Navi.exe` code that reads the `RDSTM001.DAT` header sets, the group index (`u16 size_dwords, u32 addr, u16 blocks, u32 key_min, u32 key_max, u16 n, n x (u32 parcel, u16 count)`) and the 4-byte `(node, link)` entries, and decode the unknown bits (`a` 0x4000/0x8000, `b` 0x4000/0x8000, link-record role `k & 3`, header words `3`/`122`).
  - Input: EXP-2026-11-20-M4.16e-rdstm-link-groups (C-5137–C-5139, C-5371); `tools/rdstm_links.py`; the TMC record readers of M3.7/M4.16b (`0x003bc960`, `0x003f61bc`, EU2011 build A).
  - Precheck: `python3 tools/rdstm_links.py groups RDSTM001.DAT` → `set 1: groups 3132 … all referenced 3132/3132` (the structure the reader must parse exists), and `python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe 0x003bc960` → START.
  - Signature: derived from the decode (weakest kind, say so): a loop over `u16 n` entries of 6 bytes after an 18-byte group head, a `<<11` + `<<8` address build (`(v>>8)*0x800 + (v&0xff)*0x100`), and `& 0x1fff` on both halfwords of a 4-byte entry; prefer callers of the RDSTM volume open (`0x004125a8`) by reachability (M3.23) over pattern scans.
  - Scope: `Navi.exe` sec0 (EU2011 build A) plus the DLLs it calls for TMC; L3 on one ref of table 0.
  - Done when: the reader has a VA in `docs/format/rdstm.md` and an L3 run resolves one ref of the EU card to the same (parcel, node, link) as `rdstm_links.py`; or `blocked` with the searched signature, corpus and a control.
  - Stop: after the reachability walk and two derived signatures without a hit, report `blocked` with the call tree searched.
  - Claims: C-5375–C-5379 (from M4.16e's block)

- [ ] **M4.51 — Who sends the TMC data-layer messages `0x14f4`/`0x14e4`, and what does `0x14f4` read**
  - Status: blocked · Owner: task/m4.51-tmc-14f4-senders · Critical: no
  - Step: P3
  - Blocker: `0x14f4` has no static sender (EU2011): the only send path `fn 0x003c0e68` (id `u16 @(8,req)`, `OSM_TaskSend`) has 25 static callers, each with one id literal (`0x14e4` only from `fn 0x003bcac0`), none `0x14f4`; 7 DLLs load neither id. The request is built at run time; the file/offset it reads needs a dynamic run.
  - Unblock: M4.53 (L3 data layer on a synthetic `0x14f4` request) or M8.E4 (full `Navi.exe` run with a read watch on `RDSTM001.DAT` `0xcda000`/`0xe78500`/`0xeb6200`).
  - Note (M4.53 done, 2026-11-20, rule 15): the file/offset half is answered in L3 — `0x14f4` reads `REFER001` POINT/ADDRE/INTER by its sub word, not `RDSTM001.DAT` (EXP-2026-11-20-M4.53-tmc-14f4-l3, C-5680); the sender VA is still unknown, so this block stays blocked on M8.E4.
  - Result: EXP-2026-11-20-M4.51-tmc-14f4-senders (negative census with control; `rdstm_reader_scan.py --callers-of`). C-5404–C-5408.
  - Depends: M4.49 (blocked; this is its unblocker)
  - Goal: find the requester of message `0x14f4` (the second TMC request type next to the location-record request `0x14e4`, same handler `0x004003f4`, own buffer `0x009cfbb4` in the sector reader `0x00417618`, EU2011) and the file and offsets it reads; if they are the `RDSTM001.DAT` link groups (`0xcda000`/`0xe78500` and the group data), the requester is the M4.49 reader.
  - Precheck: `python3 tools/rdstm_reader_scan.py archive/head256.img --const 0x14f4` → 7 users, all in the data layer (`0x0040dd40` … `0x00417618`); `python3 tools/callgraph.py users GRAPH OSMDLL!OSM_TaskSend` lists the static senders.
  - Signature: the message id stored into a request before `OSM_TaskSend` (static); or, dynamically, an L4 read watch on `RDSTM001.DAT` sector offsets `0xcda000`, `0xe78500`, `0xeb6200` (from the M4.16e decode — data-side, say so).
  - Scope: `Navi.exe` EU2011 senders, then OBJDLL/STDDLL if `Navi.exe` has none; L4 (M8 `ze0`) only if the static search ends without a sender.
  - Input: EXP-2026-11-20-M4.49-rdstm-group-reader (C-5375–C-5379); M3.24 dispatcher tables (C-3553); `tools/rdstm_reader_scan.py`, `tools/callgraph.py`, `tools/rdstm_links.py` (expected bytes).
  - Done when: a VA (EU2011) of the function that issues `0x14f4` (or the `RDSTM001.DAT` link-group read) and the file/offset it requests, with a control (another message id's request resolved the same way); or `blocked` with the sender census.
  - Stop: if no static sender of `0x14f4` exists in `Navi.exe` and the DLLs it imports, and no L4 run reaches TMC, report `blocked` naming the M8 prerequisite.
  - Claims: C-5404–C-5408 (from M4.16b's spare block C-5404–C-5409)

- [x] **M4.53 — L3: which file and sector does a TMC `0x14f4` data-layer request read**
  - Status: done · Owner: task/m4.53-tmc-14f4-l3 · Critical: no
  - Result: EXP-2026-11-20-M4.53-tmc-14f4-l3 — `tools/tmc_req_l3.py` mounts the EU card with `datask_l3` and hands the data-access task synthetic requests: `0x14f4` reads a `REFER001` family file chosen by its sub word (1 `POINT001.DAT` `0x36600`/`0x36700`/`0x36900`, 2 `ADDRE001.DAT`, 4 `INTER001.DAT`, 3 `FRWAY001` absent), never `RDSTM001.DAT`; control `0x14e4` sub 1 reads `RDSTM001/LCTBL001.DAT` (`0x0`, `0x1000`, `0x4600`, `0x5600`). The M4.51 chain `0x00413828`/`0x004129d0`/`0x00417618` is not entered. The "`0x14f4` = link-group reader" lead is refuted; M4.49/M4.51 stay blocked on M8.E4. C-5680–C-5686.
  - Step: P3
  - Depends: M4.51 (blocked; static census done)
  - Goal: run the data-layer path of message `0x14f4` (EU2011: dispatcher entry `0x004003f4`, id switch `0x00413828` → `0x004129d0`, sector reader `0x00417618` with buffer slot `0x009cfbb4`) in L3 on a synthetic request and record the volume, file and byte offset handed to the read helper `0x003d140c`; compare with a `0x14e4` request (control, known `RDSTM001`/`LCTBL001.DAT`). If the offsets fall in `RDSTM001.DAT` `0xcda000..EOF`, the M4.16e link groups are what `0x14f4` reads, and the caller-side parser becomes the M4.49 target.
  - Precheck: `python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x004003f4 0x00413828 0x004129d0 0x00417618` → four START; `python3 tools/va_class.py archive/head256.img --module Navi.exe --resolve-with 0x3e00200 0x009cfbb4` (state the runtime state the run must seed).
  - Signature: the read helper's arguments in the L3 trace (dynamic — the strongest kind), not a byte pattern.
  - Scope: `Navi.exe` EU2011 data layer only; volume tables seeded from the card (M9.16 map-load chain if needed). No full boot.
  - Input: EXP-2026-11-20-M4.51-tmc-14f4-senders (C-5404–C-5408), EXP-2026-11-20-M4.49-rdstm-group-reader (C-5375–C-5379), the L3 harness, `tools/rdstm_links.py` (expected offsets).
  - Done when: an L3 run reports the file and offset for a `0x14f4` request and for a `0x14e4` control request; or `blocked` naming the runtime state that could not be seeded.
  - Stop: if the data layer needs state the harness cannot seed after two attempts, report `blocked` on M8.E4.
  - Claims: C-5680–C-5689

- [x] **M4.16c — Verify `INTER`/`FRWAY` `ref` lead as aligned records**
  - Status: done · Owner: task/m4.16c-inter-frway-ref · Critical: no
  - Result: EXP-2026-11-20-M4.16c-inter-ref-aligned — negative with controls: the C-1811 enrichment (257 vs 10 uniform random over `INTER001`–`005`) is a byte-composition artifact; a byte-profile control hits more often than the real values in the byte scan (477), aligned `u32` (135 vs 55), blob-0 element +2 (30 vs 7) and table fields (15 vs 3), and the decoded M4.16e link refs stay below their control too (aligned 10 vs 30). No RDSTM key reaches `INTER`; placement goes through M4.16b/M4.16e (C-5950). `tools/inter_ref_probe.py`. C-2310–C-2314; C-1811 superseded.
  - Done when (set at close, the block had none): C-1811 tested as aligned fields against controls with the same byte make-up, and the reference decoded or the lead refuted. Met (refuted).
  - Step: P4
  - Depends: M4.16
  - Goal: test C-1811 as aligned u32 fields (not byte scan) in `INTER*`/
    `FRWAY*`, decode the mesh/link reference, and test `INTER→tile/mesh→
    coordinate` with random-key control.
  - Claims: C-2310–C-2319 (was C-1950–C-1959, already used by M2.13b)

- [x] **M4.16d — TMC location→segment placement via `TFTBL`/`reception.dat`**
  - Status: done · Owner: task/m4.16d-tmc-segment-placement · Critical: no
  - Result: EXP-2026-11-20-M4.16d-tmc-reception-table-codes — `TMC/reception.dat` lists the card's 14 (CC, LTN) pairs, one per RDSTM table; a table code is `ord(CC hex digit) << 8 | LTN` (14/14 listed, 14/14 codes carry the RDS CC of the country their records land in; shuffled countries max 8/14). With M4.16b (C-5400/C-5402) the chain (CC, LTN, location code) → RDSTM table → record → MAPAL node is closed. `TFTBL001` is absent on 2011 cards (C-122), not tested. `tools/tmc_reception.py`. C-2320–C-2323.
  - Done when (set at close, the block had none): every `reception.dat` (CC, LTN) maps to exactly one RDSTM table whose placed records lie in the country with that RDS CC, above a shuffled-country control — met.
  - Step: P3
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


- [x] **M4.22 — Identity codes: header `0x180`, `DRSTR` `0x18c`, `BICON001` version**
  - Status: done · Owner: task/m4.22-identity-codes · Critical: no
  - Depends: —
  - Note (SE 2026-11-15, supersedes the PO 2026-11-13 note): the PO note pointed the `0x18c` code table at **M4.36**, which is the unrelated `ADDRE`/tile-section-4 join. The correct unblocker is **M4.38** (SE 2026-11-15); this task stays blocked on the `0x18c` code→language anchor plus its own header-word work (M4.12 delivered the ICODE001 index it needs, not the codes).
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
  - Claims: C-5280–C-5283 (was C-2490–C-2499; fresh block for this run; C-5286–C-5289 go to M4.48)
  - Blocker: M4.38 decoded the `0x18c` codes from the firmware (Navi.exe `sdl_com_hdl_get_lang` table joined with Speech.exe's dir switch; all `SPEECH/` sets on EU 2011, US 2011 and EU 2014 matched, C-3760–C-3769, EXP-2026-11-19-M4.38-lang-code-table), except `14 17 18 19 1a`, which no table in four builds returns (firmware language table for them not found). The header fixes and the BICON001 retraction are done (EXP-2026-11-08-M4.22-identity-codes).
  - Unblock: re-open now to finish `file-header.md`/`drstr.md`/`assets.md` with the M4.38 code table (the language-matching done-when is met for every code with a speech set); `14 17 18 19 1a` stay `UNKNOWN`/`HYPOTHESIS` with the mutation named in `file-header.md`
  - Result: done — EXP-2026-11-20-M4.22-identity-codes. `identity_fields.py card` (new) reads MMAIN001/BICON001/DRSTR001 from the FAT of all four cards (EU/US 2011 full, EU 2014/2016 head + fetched clusters): every 2026-11-08 value reproduced; `header_block.py check` PASS on 8 headers, DRSTR negative exit 1; M4.38 language join PASS on all four cards incl. EU 2016 (16/16). `file-header.md`/`drstr.md`/`assets.md` carry the M4.38 code table; `0x180`–`0x183`, `14 17 18 19 1a` stay `UNKNOWN` with their mutations. Only `Navi.exe` imports `OBJ_DriveInfo_readDataVol`, and only fn `0x00377ae0` (EU2011) loads the thunk; the `0x18c` reader is M4.48 (C-5280–C-5283).

- [ ] **M4.48 — Trace the `Navi.exe` reader of `MMAIN001` `0x18c` (map-language list)**
  - Status: blocked · Owner: task/m4.48-drstr-18c-reader · Critical: no
  - Step: P0
  - Depends: M4.22 (done), M4.38 (done)
  - Goal: find the EU2011 `Navi.exe` code that reads the `0x18c` language list from the `MMAIN001` header copy and run it in L3, so the code→language reading becomes a firmware verdict instead of a value join.
  - Precheck: `python3 tools/sh4xref.py archive/head256.img Navi.exe --to 0x01205040` lists the 4 functions that load the header copy (`0x00377ae0`, `0x003796bc`, `0x003798bc`, `0x0037a2c0`); `python3 tools/nk_decomp.py pdata archive/head256.img --module Navi.exe 0x003796bc 0x003798bc 0x0037a2c0` gives `START` for each.
  - Scope: EU2011 build A `Navi.exe` and OBJDLL; signature from the data (byte-swapped u16 pairs at `+0x18c`, `3f` terminator, `cmp/eq #63`), not from the doc; excludes the meaning of `14 17 18 19 1a`.
  - Input: EXP-2026-11-20-M4.22-identity-codes (consumer census), EXP-2026-11-19-M4.38-lang-code-table, `tools/identity_fields.py card`, `tools/lang_code_table.py`.
  - Done when: one function VA (EU2011, `pdata` `START`) is shown to read `+0x18c` of the header copy, and an L3 run of it on the EU 2011 header returns a different result when `05` is replaced by `3f`.
  - Stop: if none of the four loaders nor their callees reads `+0x18c..+0x19f` within two call levels, set `blocked` with the call tree in the EXP.
  - Claims: C-5286–C-5289
  - Blocker: no EU2011 code reads `0x18c..0x1a0` statically: OBJDLL's field table (`0x01e33290`) names it index 9, and none of 31 `getSize`/`getOffset`/`readDiscVol` call sites (all importers + OBJDLL) asks for index 9; the whole-header copies reach 40 functions to depth 2 with no constant access in `0x18c..0x1a0` (bounds reader `0x003f7008` at `0x184..0x18a` is the positive control). No function VA exists to run in L3.
  - Unblock: M4.50 (read watch on the header copies in a full `Navi.exe` run, or a bench `05`→`3f` mutation).
  - Result: blocked — EXP-2026-11-20-M4.48-datavol-18c-reader. `tools/datavol_trace.py` (new: `table`, `calls`, `taint`, `--selftest`). Header path (EU2011): `0x0041a438` reads `MMAIN001.DAT` → `0x0041a304` swaps + `writeDataVol` → `0x00377ae0` `readDataVol`/`writeDiscVol` → five `readDiscVol(…, 20, …)` copies; field requests: indices 3/4/7/8 only (C-5286–C-5289).

- [ ] **M4.50 — Watch run-time reads of the `MMAIN001` `0x18c` language list**
  - Status: open · Owner: — · Critical: no
  - Step: P0
  - Depends: M4.48 (blocked, static negative), M8.E4 (full `Navi.exe` run) — or a car/bench slot
  - Goal: decide whether any EU2011 code reads header bytes `0x18c..0x1a0` at run time, now that a static census found no reader (C-5287, C-5288).
  - Precheck: `python3 tools/datavol_trace.py calls archive/head256.img --field 0x18c --size 20` still exits 1 (no field request), and the L4 run reaches fn `0x00377ae0` (EU2011) with the header in `0x01205040`.
  - Scope: EU2011 build A; read watch on `0x00e23cc0`, `0x01205040`, `0x00625668`, `0x009c9600`, `0x009c8600` and the block `0x00d8b070` points at, bytes `+0x18c..+0x1a0`, from card insert to map display and a language change; excludes the meaning of codes `14 17 18 19 1a`.
  - Input: EXP-2026-11-20-M4.48-datavol-18c-reader (call tree, seeds), `tools/datavol_trace.py`, `tools/read_watch_l3.py` (watch pattern), M8.E4.
  - Done when: the watch reports the PC of every read of `+0x18c..+0x1a0` (or `NO HITS` with a positive watch hit on `+0x184` by fn `0x003f7008` in the same run); if a reader is found, an L3 run of it with `05`→`3f` gives a different result.
  - Stop: if the L4 run cannot reach `0x00377ae0`, set `blocked` and name the missing peripheral/import.
  - Claims: C-5470–C-5479

- [x] **M4.27 — Decode bit-packed / non-zlib `POINT` pages**
  - Status: done · Owner: task/m4.27-point-index-pages-r3 · Critical: no
  - Step: P4
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
  - Result: `docs/experiments/EXP-2026-11-20-M4.27-point-census-fine-position.md` (C-2676–C-2679; r2 partial result: EXP-2026-11-08-M4.27-bitpacked-point-pages-r2, C-2670–C-2675). New `tools/point_census.py` (`--selftest`, 32 checks) walks every structure of a POINT `.DAT` from its directory: all 44 files of EU 2011 and US 2011 (3,545,547,776 B) have 0 unaccounted bytes. The "undecoded" part is name tries, index chains (key + ordinal of a name record: 28,295,255/28,295,255 keys found in their record), spatial trees, the US phone B-tree (7,018,762/7,018,762 keys equal the `INFORMATION` number) and the `INFORMATION`/`ADM` tables; none has a position of its own. The spatial-tree leaves repeat bytes 6–9 of the name record (10,718,316/10,718,316), which gives the fine position: copy-A low nibble is `11xx`, `u = (v & ~15) + 4·(v & 3) + fine/512`, longitude origin 52736. On the 16 M4.8b references: median 115 m against 3,558 m, closer 16/16. Re-opens M4.8b and M4.28; follow-ups M3.34, M4.61, M5.63.

- [x] **M4.37 — Prove or refute that bit-packed `POINT` pages carry coordinates (one-command control)**
  - Status: done · Owner: task/m4.37-point-bitpack-coords · Critical: yes · Pair: required
  - Result: EXP-2026-11-19-M4.37-point-bitpack-coords — NO COORDINATES in bit pages: `point_bitpack_decode.py --coord-test IMG` (EU 2011, 32 alignments) gives 0 of 1,212 bit pages bounds-pass (POINT002 186, POINT008 580, POINT029 446); name-page positive control passes and phone-page negative control fails in all three shards. The raw (non-stream) region is a 16-byte `0x0008` spatial index whose finer pairs are the copy-A ids (`raw-index`: 100/97.7/92.6 %, shifted control 0 %), so there is no finer position field; M4.8b re-blocked on "format carries no sub-unit coordinate". C-3750–C-3755.
  - Depends: — (`tools/point_bitpack_decode.py`, `tools/point_walk_l3.py` on `main`; M4.27's partial decoder is a prerequisite in code, not an unreachable claim)
  - Note (SE 2026-11-15): `M4.8b` (Critical: yes) is blocked asking to "decode bit-packed POINT page grammar", but the bit-pack work is owned by `M4.27` (Critical: no) whose own Unblock only asks to decode *more classes*; neither asks the yes/no question "does any bit-packed page encode a 0..2047 coordinate at all?". Answering that first is cheap (the decoder and the 0..2047 test already exist) and decides whether `M4.8b` is impossible-by-format or just blocked on more decoding.
  - Goal: for the bit-packed (non-`78 9c`) pages of `POINT002/008/029`, test mechanically whether any page encodes a `0..2047` (or `0x3ff`/`0xfc00`-masked) coordinate pair, with a positive and a negative control, so `M4.8b` either gets its grammar pointer or is re-blocked on "these pages are non-coordinate".
  - Precheck: `python3 tools/point_bitpack_decode.py --selftest` passes; the tool already classifies POINT002 `747 name/1796 bit (1598 phone-us-fixed16 coord=no)`, POINT008 `1359/3163`, POINT029 `208/446` (M4.27 EXP); `python3 tools/point_walk_l3.py --selftest` passes (the `0x3ff`/`0xfc00` walker, C-2129).
  - Scope: `REFER001/POINT002/008/029` bit pages, EU 2011 only; run every decoded bit page through the C-2129 packed-`u16` test (`0..2047` after masks) and record the false-positive rate on a known phone page (negative control) and a known coordinate page from the inflated `78 9c` stream (positive control). No writer, no new format claim unless a coordinate page is found. Extend `tools/point_bitpack_decode.py` with `--coord-test`, do not fork a second decoder.
  - Input: `tools/point_bitpack_decode.py` (`--selftest`), `tools/point_walk_l3.py` (the C-2129 masks), M4.27 EXP (`docs/experiments/EXP-2026-11-08-M4.27-bitpacked-point-pages-r2.md`), M4.8b EXP, `docs/format/refer.md` §POINT.
  - Hints: the M4.27 EXP already sampled "coord-like" scans (0/50 phone, 0/50 unknown) but by a heuristic, not the C-2129 mask test — that is the unclosed gap. A page that passes the mask test but fails the geographic-bounds check (`lat/lon` from the COORD001 formula) is not a coordinate page; report both counts. The 72.2% non-zlib raw payload is in scope only if the bit-page test is clean.
  - Done when: `point_bitpack_decode --coord-test <IMG>` prints, per page class, `pages tested / mask-pass / bounds-pass`, the positive control passes on a known `78 9c` coordinate page, the negative control fails on a phone page, and the EXP states `COORDINATES FOUND` (with the grammar) or `NO COORDINATES` (with the test and counts); `M4.8b`'s Unblock is updated to cite this EXP or set to `blocked (format carries no coordinate)`.
  - Stop: if no bit page passes bounds after the mask test on all three POINT files, record `NO COORDINATES`, point `M4.8b` at the inflated-stream path only, and do not decode more classes "just in case".
  - Claims: C-3750–C-3759

- [x] **M4.38 — Identify the `0x18c` language-code table (unblocks M4.22)**
  - Status: done · Owner: task/m4.38-lang-code-table · Critical: no · Pair: required
  - Depends: — (M4.12's `tools/coord_zcode_icode.py` is on `main`; M4.22's header-word work is independent of this code-table search)
  - Note (SE 2026-11-15): `M4.22` sat blocked with "new task needed (none on the board yet)" since 2026-11-08; PO's 2026-11-13 note pointed it at `M4.36`, which is the unrelated `ADDRE`/section-4 join (mis-link, fixed in the same pass). This task is the actual missing unblocker, split out so `M4.22`'s header-word work does not wait on it.
  - Goal: map each byte of the `0x18c` code list (`05 04 02 07 0a 06 08 14` on EU 2011, 17 codes on EU 2014) to a language and its `SPEECH/` set, or prove no on-card anchor exists and name the firmware table that would settle it — so `M4.22` can finish `file-header.md`.
  - Precheck: `python3 tools/coord_zcode_icode.py --selftest` passes; the code list is `05 04 02 07 0a 06 08 14` in EU 2011 `MMAIN001`/`BICON001` and 17 codes in EU 2014 (EXP-2026-11-08-M4.22-identity-codes, counts agree US 2/2, EU 8 vs 7 and 17 vs 16); `DRSTR001` `0x18c` is a node `listing_offset`, not a language list (C-2493) — do not re-chase it.
  - Scope: the ICODE001 per-language index (M4.12 located 7 EU + 2 US country-chain root byte offsets but not the root-pointer index table) and a firmware language-table search only if the on-card route fails. Tools: `tools/coord_zcode_icode.py` (extend, do not fork), `tools/diff_years.py --partial` for the EU 2011↔2014 code delta, `tools/sh4scan.py` for a `SPEECH`-selection table. No new writer; no vendor bytes committed.
  - Input: `tools/coord_zcode_icode.py`, `docs/format/coord-zcode-icode.md`, `docs/format/file-header.md` Identity fields, `docs/format/assets.md` (`SPEECH/` sets), `docs/research/sources.md`, EXP-2026-11-08-M4.22-identity-codes, OQ-44.
  - Hints: the EU 2014 list is the 8-code 2011 list plus 9 more in a fixed order — a code→language map that explains the appended codes is stronger than one fitted to EU 2011 alone. `SPEECH/` directory names are the only on-card language labels; if no code aligns with their order, say so and name the firmware table shape (a `u8`-keyed `language → directory` array) as the falsifiable next step rather than fitting a permutation.
  - Done when: an EXP states each `0x18c` code's language and its `SPEECH/` set with an anchor (a directory name, a firmware table VA via `sh4scan`, or a mutation control), OR states "no on-card anchor" with the negative control and names the firmware table to search; `M4.22`'s Unblock/Blocker is updated to cite this EXP; `claims_check.py` OK.
  - Stop: if neither an on-card nor a firmware anchor exists, record the negative (counts agree but no code→name link) and leave `M4.22` blocked on "firmware language table not found", not on "new task needed".
  - Claims: C-3760–C-3769
  - Result: EXP-2026-11-19-M4.38-lang-code-table. The codes are Navi.exe `sdl_com_hdl_get_lang` values (EU2011 fn `0x003c0228`, rows `0x00045d90`; EU2014 `0x003f3c34`/`0x00047a78`), default `3f`; Speech.exe maps the same `OBJ_Setting_readExpLanguage` setting to the `SPEECH/` dir. `02` EN-UK/BE, `03` EN-US/US, `04` FR (FR, CF), `05` GE, `06` SP, `07` IT, `08` PT, `09` EL (cross-build), `0a` DU, `0c` SV, `0d` DA, `15` FI, `16` NO (+ `01` JP, `0b` RU, `0e` ZH, `0f` KO). `tools/lang_code_table.py join`: EU 2011 7/7, US 2011 2/2, EU 2014 16/16 dirs, shifted ±1 and no-Navi-table controls fail. `14 17 18 19 1a`: no row in four builds (`rows` scan) — named as the open step; the reader of `0x18c` is not traced. `claims_check.py` OK.

- [ ] **M4.28 — Explain the POI latitude residual (+2.8 km) on a known entrance**
  - Status: open · Owner: task/m4.28-poi-lat-residual-r2 · Critical: no
  - Step: P4
  - Blocker: M4.27 (bit-packed POINT wider sample) unavailable in this session; M4.28 precheck not satisfied on M4.8b's 16 inflated-stream POIs — no POI with a reliably known, checkable entrance-vs-centroid/reference coordinate separation from allowed non-OSM sources identified (airports share ARP ref; building landmarks have sub-packed-unit separation, too small for the km-scale residual). Stop triggered; H1/H2 untestable. Analysis narrows C-1903 (dlat 132–6401 m, 48×, not a uniform fixed offset) but C-1904 not confirmed/narrowed-to-verdict/retracted.
  - Unblock: re-opened 2026-11-20 by M4.27 (C-2679): the +2.8 km latitude residual is explained without an entrance test — the copy-A low nibble is `11xx` (marker bits, 4-unit sub-cell), so the 1-unit reading is off by up to 15 units; with the fine fields the 16 references fit to a median of 115 m. Left to do here: update or retract C-1903/C-1904 against `tools/point_census.py refs`, and close.
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
  - Step: P3
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

---

- [ ] **M4.36 — Link `ADDRE`/`POINT` records to the tile section-4 index (road-name and place lookup key)**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P3
  - Depends: M3.13 (ADDRE reader), M3.9 (section-4 index, done), M4.16b
  - Goal: the L2 reader model today decodes tile section 4 (admin/place-name index) and the odd name section separately, but no task proves how an `ADDRE` id resolves to a *named* street through the section-4 index. Routing and map display need that join; without it a generated Polish tile renders roads with no names even when every record is structurally valid.
  - Precheck: `python3 tools/ze0-viewer/harness.py info B48R058R.DAT` shows non-zero section-4 entries; `python3 tools/addre_reader.py --selftest` (or M3.13's tool) passes; on a factory EU tile, one known street name from `B48R058R` decodes through section 4 to its `ADDRE` record.
  - Scope: factory EU 2011 `B48R058R` and one US tile; `docs/format/refer.md` §section-4, `tile section 4` claim rows, `tools/ze0-viewer` readers. Not: the `REFER002` EV layer, not POI. No new vendor bytes committed — offsets/counts/hashes only.
  - Input: `docs/format/tile.md`/`refer.md` section-4 pages, M3.9 EXP, M3.13 ADDRE reader, `tools/ze0-viewer/tools_ze0`, US `ADDRE`/`POINT` share ids (AGENTS "Format facts").
  - Hints: AGENTS already states `ADDRE`/`POINT` share ids and the join is street + house number; the open question is which section-4 field indexes the name (offset vs ordinal) and whether US stores `ltntbl.dat` case-sensitively. Start with one street whose name is unique in the tile (positive control) and one absent street (negative).
  - Done when: an EXP table `tile / section-4 entry / name / ADDRE id / how resolved` covers ≥ 10 names on EU and ≥ 3 on US with a negative control, `docs/format/refer.md` gains the join, and the viewer `info` prints the resolved name for at least one record. Reader-coverage row updated; L3 reader VA named if M3.13 has one.
  - Stop: if the join is not one-to-one, record the ambiguity classes (same name on two streets, unnamed ways), and stop at the mapping table.
  - Claims: C-3670–C-3679

- [x] **M4.39 — Route-link id: what in a `MAPAL001` tile section 2 can a `LCTBL001` road or an `ADDRE` record be joined to**
  - Status: done · Owner: task/m4.39-route-link-id · Critical: yes · Pair: required
  - Depends: M5.37 (the L2 graph model this task needs to name nodes/links), M4.31 (the negative join search this narrows); M3.6 (which sections the router reads, done)
  - Goal: routing needs a stable key from a displayed road name/record back to the graph edge the router uses. M4.31 proved there is no `LCTBL↔RDSTM` join and M3.7 showed `RDSTM001` is TMC, not routing; nobody has asked whether section 2 itself carries an id an `ADDRE` name can reach. Without it the map routes on an anonymous graph and "route across the moved road" (M6.7) cannot be aimed at a chosen OSM way.
  - Precheck: `python3 tools/tile_diff.py B48R058R.DAT --section 2` lists section-2 records (M4.23/M4.24 framing); `python3 tools/ze0-viewer/harness.py info` shows section 2 non-zero; `grep -rn 'link_id\\|link_id\\|edge_id' tools/ docs/format/` prints nothing outside the M4.31 negative, i.e. the key is unnamed today.
  - Scope: factory `B48R058R` (and one second tile) section 2 only, offline: enumerate every field that could be a link/node id, test each as a join key against the name layer (section 4 + `ADDRE` from M4.36) and against `LCTBL001`, with a shuffle null control. One EXP table + one candidate key or a negative. No writer, no firmware run; do not re-open M4.31's RDSTM test.
  - Input: `tools/tile_diff.py`, `tools/rd_restrictions.py` (section-2 framing), M4.23/M4.24 grammar, M4.31 EXP (negative), M4.36 (name layer), `docs/format/map-tiles.md` §section 2, `docs/format/refer.md`.
  - Hints: section-2 part b is not decoded (M4.23 open), so restrict to record-level fields that survive the framing; a key that only works on one tile is not a key. The M4.31 lesson: state the join key and corpus size up front, and treat row order as a last resort, never a result. If the only id is a node coordinate pair, say so and propose the coordinate join as the hypothesis for M4.36 to test.
  - Done when: the EXP lists every section-2 field tested, the join rate against the name layer and against `LCTBL001` for each, the shuffle/null baseline, and either names a key that beats its null (with a second-tile control) or records the tested fields as a controlled negative; `docs/format/map-tiles.md` gets the field table.
  - Stop: if no field survives the framing on two tiles, record the negative with the null and stop; do not fit a key from row order.
  - Falsifier: a claimed key scores no better than its shuffled null, or works on `B48R058R` and not on the control tile without a named reason.
  - Claims: C-5150–C-5156 (block C-5150–C-5159; C-5157–C-5159 handed to M4.46)
  - Result: EXP-2026-11-19-M4.39-route-link-id (C-5150–C-5156, `tools/route_link_join.py`): the key is `(parcel code, class & 0xf, entry word 3 & 0x1fff)` — it names the drawn section-1 link with an end at the entry's node for 99.9 % of entries on `B48R058R` (4,970,122) and on the control `B38R068R` (1,590,948), against 6.1 % with the field shuffled and ~0 with another parcel's shapes; node `(x, y)` keys nodes (100.0 % vs ≤ 0.05 %); w4/w5/a/b/node indices are not keys (≤ 7.9 % vs nulls 0.8–4.2 %). ADDRE refs reach it through the drawn point (Andorra on `B38R068R` 2,125/2,125 land, 2,112 on the named street vs 406/2 rotated-parcel null; Germany on `B48R058R` 44,631/44,631, 44,576 named vs 7,741/180). `LCTBL001` has no numeric key (best hit/null 1.43 at 0.1 %); name text only, median 8 records per name. Field table in `docs/format/map-tiles.md` ("Route-link key"). Section-2 decoding used: `clarion_rd`/`rd_check` on `main` (M5.37 merged meanwhile; not needed). New: M4.46.

- [ ] **M4.40 — Tile section 2 (route graph) grammar read from the router's reader, not guessed from bytes**
  - Status: blocked · Owner: task/m4.40-sec2-field-table · Critical: yes · Pair: required
  - Blocker (2026-11-20, second run): the router's reader does not read section 2 — `RGD_DATA READ` `0x004266ec` (EU2011) requests kind `0x40`, which the data-access task serves with the parcel's **section-4** record (L3 on the EU card, C-5921); section 2 is requested with kinds 8/`0x10` by the route path finder `RPF_PreMap_start` `0x00336bf0` (C-5923), whose reply points at units 0 and 2 of the record (C-5922). The section-2 field table must be read from the route path finder's reply handler (M4.55).
  - Unblock: M9.65 (M4.55 is blocked on the harness binding it needs: STDDLL exports for Navi.exe thunks)
  - Blocker (resolved 2026-11-20 by M4.54, kept as a note): the reply `0x14b6` is copied by `0x004268c0` into a per-slot buffer read by `0x00422eac`; M4.54 ran that path in L3 and mapped the four words it reads to part-a fields (C-5710–C-5717).
  - Start (from M4.54; premise retracted by C-5924, the buffer holds section 4): `0x00422eac` on factory `B48R058R` section-2 record `0xb91d078` (`k=221`, part-a node 7 header; `k+6` = entry 0 `id`, `k+7`/`k+15` = entry 0/1 `cls`, `k+d` = entry 0 `a`). Read the part-a table in `docs/format/map-tiles.md` §"What the four words are (M4.54, L3)" and extend it to the whole record; `k`'s real source `0x00424464(19, …)` is still unknown (the census shows `k` is not always a node header, C-5714/C-5716).
  - Step: P2
  - Note (M3.25, 2026-11-19): the block decoders are named and run: `0x004157dc` picks one of eight (`0x00414644`, `0x00414930`, `0x00414dbc`, `0x00415330` ran; C-4691). `python3 tools/datask_l3.py mount … --bytes --json out.json` lists every byte each decoder loaded per block: the first byte not loaded bounds a record, and the decoder's branches are the grammar. Start from `0x00414930` (largest blocks).
  - Note (H112, 2026-11-19): **numbers in this block are corrected by C-4622:** `reach g.json 0x004266ec` now prints `reaches 27 functions, 1 unresolved indirect calls` (the root is counted; use that in the Precheck), and the subtree has no file-mapping import. The router differs from the renderer by three small callees only (`0x00425c5c`, `0x00425cb0`, `0x00425cf4`; `0x00425cf4` calls `OSM_SramSet`), and the shared `0x0041ee14` calls `OSM_TaskSend`. So this block's `Stop` ("handed on by message") is the likely first result: do that check first (one hour with `sh4dis` on `0x0041ee14`: which message id, which receiver task), then follow the receiver. The section-2 grammar is then read from the code that handles the *reply*. Data-side help from M4.41: `B60R060R` 2011 vs 2014 has 7 added section-1 streams — the smallest known section-2 delta.
  - Depends: M3.25 (entry and arguments of the tile reader; this task can start from the VAs below without it), M9.38 helps (read-watch)
  - Goal: a generated map cannot route until we can write section 2, and its part b has resisted three byte-level attempts (M4.23, M4.24, M4.3 blocked). ~~The code that parses it is small and isolated: the router data reader `0x004266ec` (EU2011, M3.6) reaches 27 functions with one unresolved indirect call.~~ (corrected 2026-11-20 by C-5921/C-5927: `0x004266ec` fetches section 4 and reaches 30 functions; the section-2 reader is the route path finder's reply handler, M4.55.) Read the grammar off the code that walks the kind-8 reply (M4.55).
  - Precheck: `python3 tools/callgraph.py reach g.json 0x004266ec` prints `reaches 30 functions, 1 unresolved indirect calls, 23 distinct imports` (C-5927; C-5640 said 27, the 48 came from the retracted C-4284) — that subtree fetches section 4 (C-5921), the section-2 requester is `0x00336bf0` (`reaches 14 functions`, C-5927; M4.55); `python3 tools/callgraph.py callers g.json 0x004266ec --depth 3` shows `0x00426d3c`, `0x0042810c` and `0x00427870` ← `0x00427144`/`0x00427c90` ← `0x00427a34`.
  - Scope: the code that walks the kind-8 reply (M4.55; was "the 27-function subtree" of `0x004266ec`, which fetches section 4, C-5921), EU2011. Output is a field table for the section-2 record (offset, width, endianness, meaning or `unknown`, the VA that reads it) and the loop structure (what counts records, what ends one). Check each field on factory `B48R058R` and one second tile with `tools/tile_diff.py --section 2`. No writer.
  - Input: `tools/sh4dis.py`, `tools/callgraph.py`, `tools/rd_restrictions.py` (the framing M4.23/M4.24 already have), EXP-2026-11-06-M3.6 (MAP_DATA `0x00425f40` renderer / RGD_DATA `0x004266ec` router, shared `0x0041ee14`), `docs/format/map-tiles.md`. ~~The subtree imports `CreateFileMappingW`/`MapViewOfFile`: the tile is memory-mapped, so the reader takes a pointer — the easiest kind of function to run in L3.~~ (false: C-4284 retracted by C-4622; no mapping import, C-5640)
  - Hints: the renderer subtree `0x00425f40` has about the same size (27 for the router) and shares `0x0041ee14` — diff the two callee sets first; what only the router calls is the section-2 parser. In SH-4 a record field read is `mov.b/mov.w/mov.l @(disp,Rn)` off one base register: list the displacements per function and you have the struct. A Ghidra decompile of these 27 functions (M9.2, runnable on Marek's host) turns days into hours; without it use `sh4dis` and the read-watch tracer. Run the entry in PySh4 with the factory tile mapped and watch which bytes of section 2 are read and in what order: the read order is the grammar.
  - Done when: the field table is in `docs/format/map-tiles.md` with the reading VA per field; `tools/rd_restrictions.py` (or a new `tools/sec2.py`) decodes part b of both tiles with 0 bytes unexplained or lists the unexplained ranges; M4.23/M4.24/M4.3 get an `Unblock:` line pointing here.
  - Stop: if the subtree turns out to hand section 2 to another task by message (an `OSM_TaskSend` with the buffer), name the receiver and stop — that is the next subtree.
  - Falsifier: a field the table gives does not vary where the two tiles' roads differ, or the L3 run reads bytes outside section 2 only.
  - Claims: C-5920–C-5929 (was C-5640–C-5649; fresh block for this run)
  - Result: EXP-2026-11-20-M4.40-request-kinds (blocked, C-5920–C-5927, `tools/datask_req_l3.py`). The data-access task, run in L3 on the EU 2011 card with a declared client row, maps request kind to section index through the table at `0x179b20` (`0x00408f9c`): kinds 1/2/4 → section 1, 8/`0x10`/`0x20` → section 2, `0x40` → the third section = **section 4**. Kind `0x40` (the router's) read section-4 records `B48R058R` `0x113ca000` and `B30R058R` `0x805900` (signpost text `0=POZNAN:KALISZ:(36):RAWICZ`, `…POZZALLO NORD…SIRACUSA`; reply `+24` = header word 6 = name offset); kind 8 read section-2 records (`B48R058R` `0x1095c000`, `0x109af600`; `B30R058R` `0x567400`) and replied `+16` → unit 0 (word 27), `+24` → unit 2; kind 4 → section 1. Controls: parcels without section 4 → status 4; no client row → status 9, no read. M4.54's part-a reading of the `0x00422eac` words is retracted (C-5713–C-5715 → C-5924): its `k` passes the gate in 24,483/65,274 section-2 records by chance (0.27 % of words; section 4 0.28 %). Precheck now prints 30 functions (C-5927). M4.23/M4.24/M4.3 stay blocked; their reader is M4.55's. New: M4.55, M4.56. `map-tiles.md` gains "Which section each request kind fetches"; `reader-coverage.md` rows 18/19.
  - Note (first run, 2026-11-20): EXP-2026-11-20-M4.40-sec2-router-grammar (blocked, C-5640–C-5649). Precheck as corrected: `reach 0x004266ec` → 27 functions, 1 unresolved, 23 imports, **no file or file-mapping import**. The router reader builds a list of `(mesh id, DIVID)` requests and sends `0x14b5` sub 2 with data kind `+16 = 0x40` via `0x0041ee14` → `OSM_TaskSend` to the data-access task; the renderer `0x00425f40` (control) sends the same message with kind `4`. Receiver: message-table row `0x14b5` → `0x004066ac` (140-function subtree, kind passed to `0x00408480`). Reply (navigator review): `0x14b6` kind 64 → `0x00427144` → `0x004268c0` copies ≤ `0x1f400` B into the slot buffer reserved by `0x00425cb0`; the only reader of that buffer is `0x00422eac` (← `0x0043fabc`/`0x0043fba8` ← `0x00440e00`), which reads words `k+15` (`&0x0f00 == 0x0900`), `k+7`, `k+6` = `d` and `k+d`. No field table: buffer content and `k` are open (M4.54). `map-tiles.md` gains "The router reader asks; it does not parse" with the reply path.

- [x] **M4.54 — Drive the router's section-2 reply path in L3: fake `0x14b6` into `0x004268c0`, read-watch `0x00422eac`**
  - Status: done · Owner: task/m4.54-sec2-read-watch · Critical: yes · Pair: required
  - Depends: M4.40 (blocked on this; request, reply and reader named), M9.38 helps (read-watch)
  - Goal: M4.40 found that the router (EU2011) requests section 2 by `0x14b5` kind `0x40`, receives it as `0x14b6` kind 64 in `0x004268c0` (copy of ≤ `0x1f400` B from message `+20` into a slot buffer, `*0x00ec3954` entry `+4`) and reads it only in `0x00422eac`, which reads `u16` words `k+15`, `k+7`, `k+6` = `d`, `k+d` with `k` from `0x00424464(19, …)`. Find which factory section-2 bytes those words are, which is M4.40's goal.
  - Precheck: `python3 tools/callgraph.py build archive/head256.img --module Navi.exe -o G`, then `python3 tools/callgraph.py reach G 0x004066ac` prints `reaches 140 functions, 1 unresolved indirect calls, 21 distinct imports`; `python3 tools/sh4dis.py archive/head256.img Navi.exe --image-start 0x200200 --va 0x00422fbc --count 14` shows `mov.l @(4,r2),r10` at `0x00422fc0`.
  - Scope: a new module (e.g. `tools/rgd_reply_l3.py`; do not edit `datask_l3.py`/`vcard_l3.py`) that sets up one router slot (mesh id and `DIVID` of factory `B48R058R`), runs `0x004268c0` with a `0x14b6` message (kind 64) whose `+20` points at that tile's section-2 block (stub `0x003edf5c` to return its length if the model lacks the task's tables, and say so), then runs `0x00422eac` from `0x0043fabc`'s arguments with a read-watch on the buffer, and maps each read buffer word to its tile offset. Control: a buffer filled with a non-section-2 block (section 1) must fail the `0x0900` test or read different words. EU2011 only.
  - Input: EXP-2026-11-20-M4.40-sec2-router-grammar (C-5640–C-5649, reply path C-5646–C-5648), `0x00424464` (UNKNOWN; source of `k`), `docs/format/map-tiles.md` §"The router reader asks; it does not parse", `tools/rd_restrictions.py`/`clarion_rd` (the known part-a layout, a cross-check), M4.39 key `(parcel, class & 0xf, w3 & 0x1fff)`.
  - Done when: the run lists, for one factory section-2 block, the tile offset and value of each word `0x00422eac` reads (`k+15`, `k+7`, `k+6`, `k+d`) and what `k` indexes, with the section-1 control; then M4.40 returns to `open` with `0x00422eac` and those offsets as its start.
  - Falsifier: with a real section-2 block `0x00422eac` never passes the `0x0900` test, or the words it reads are not inside the copied block.
  - Stop: if `0x00422eac` cannot be reached with a consistent `0x00424464` table after two model fixes, record what it reads instead and stop.
  - Claims: C-5710–C-5719
  - Result: EXP-2026-11-20-M4.54-section2-read-watch (C-5710–C-5717, `tools/rgd_reply_l3.py`): the reply path was driven for factory `B48R058R` section-2 record `0xb91d078` (`k=221`) — `0x004268c0` copies the block's plain 3508 B into the slot buffer and sets state 2 (a pass-through; it stored a section-1 block too), and `0x00422eac` clears the `0x0900` gate and reads `k+15` block word 236 `0x0919` (node 7 entry 1 `cls`), `k+7` word 228 `0x0717` (entry 0 `cls`), `k+6`=d word 227 `0x0008` (entry 0 `id`), `k+d` word 229 `0x003b` (entry 0 `a`), `out=7`; `k` is part-a node 7's header word 0 (`x=0x4fd`, count 3). Section-1 controls at the same `k` (`0x176a800`, `0x66700`) and a declared `k=0` all `GATE-REJECT`; second tile `B30R058R` `0x5759f4` passes (`k=78`, there `k` is an entry's `a`), `B28R070R` 0/303 has a passing `k`. Census 24,483/65,274 records pass on `B48R058R`; `d` = entry 0 `id` 4513/4513 but `k+d` = entry 0 `a` only 92/4513 (C-5715). `k`'s real source `0x00424464` and the reply's block granularity stay open — M4.40 returns to `open` with these offsets; also `map-tiles.md` word table, precheck `0x004066ac` is 145 functions not 140 (C-5718).

- [ ] **M4.55 — Section-2 reader in the route path finder: drive the kind-8/`0x10` reply and read-watch unit 0**
  - Status: blocked · Owner: task/m4.55-rpf-section2-reader · Critical: yes · Pair: required
  - Step: P2
  - Depends: M4.40 (blocked on this; requester and reply named)
  - Goal: M4.40 found that section 2 is not read by the router (`RGD_DATA` fetches section 4) but requested by the route path finder `RPF_PreMap_start` `0x00336bf0` (EU2011) with kinds 8 and `0x10`, and that the data-access task replies with pointers to units 0 and 2 of the level-1 record (C-5922, C-5923). Find the RPF code that receives that `0x14b6` reply and walks unit 0, and read the section-2 field table off it (M4.40's goal).
  - Precheck: `python3 tools/datask_req_l3.py request archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --position 51.70,17.45 0xa68cd68c:0:8` prints `+16 … word 27 = unit 0`; `python3 tools/sh4dis.py archive/head256.img Navi.exe --image-start 0x200200 --va 0x00336c88 --count 60` shows `mov #8` at `0x00336cba` and `mov #16` at `0x00336d06`; `python3 tools/callgraph.py callers G 0x00336bf0 --depth 3` names the RPF task loop.
  - Scope: EU2011 build A, the RPF task: its message dispatch for `0x14b6`, the function that takes list entry `+16`/`+24`, and every function that loads through those pointers; one factory level-1 record of `B48R058R` and one of `B30R058R`. Signature source: the L3 reply (C-5922), not the format doc. No writer; US2011 only as a follow-up.
  - Input: EXP-2026-11-20-M4.40-request-kinds, `tools/datask_req_l3.py` (`Client.request` returns the reply in guest memory: hand that list to the RPF handler), `tools/rgd_reply_l3.py` (pattern for a reply-path harness with a read-watch), `tools/ze0-viewer/tools_ze0/clarion_rd.py` (the unit-0 parse to compare against), `docs/format/map-tiles.md` §"Which section each request kind fetches".
  - Hints: the RPF sends to the data-access task with its own task id at `+12`; the reply comes back as `0x14b6` with kind 8 or `0x10` in `+16`. Search the `0x14b6` loaders (`mov.w` pools holding `0x14b6`) inside the `0x0033xxxx` RPF range for a dispatcher that branches on kind 8. Kind `0x10` returned "no data" for a level-1 mesh: try the level-2 parcel code. Run the handler on the real reply and read-watch the two pointers: the read order is the grammar.
  - Done when: an EXP lists, for one factory record, every unit-0/unit-2 word the RPF code reads with the reading VA (EU2011), the field table goes into `docs/format/map-tiles.md`, and a control (a section-1 record behind the same pointers) is read differently or rejected; then M4.40 returns to `open` (or closes with that table) and M4.23/M4.24/M4.3 get `Unblock:` lines pointing at it.
  - Stop: if the RPF reply handler cannot be reached without a model of more than two RPF globals, record the call chain and the globals and set blocked on an M9 harness task.
  - Falsifier: the RPF handler reads no word through `+16`/`+24`, or reads bytes outside the record's units.
  - Claims: C-6020–C-6029
  - Blocker: The RPF reply consumer 0x003367a0 faults at 0x003367c2 on an unmodelled import STDDLL!STD_MeshPnt_isValid (thunk 0x003d1640 -> IAT 0x0055da88) before its first unit-0 read; vcard_l3.py has 81 import models and none is a STDDLL mesh export. Same exports run in poi_position_l3.py, so it is a harness binding gap, not a firmware limit.
  - Unblock: M9.65
  - Result: EXP-2026-11-21-M4.55-rpf-consumer-import-block (negative); call chain + kind-8 reply recorded, 0 unit-0 reads

- [ ] **M4.56 — Tile section 4 (route guidance) grammar from the router consumer `0x00422eac`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P2
  - Depends: M4.40 (section 4 is what the router's `RGD_DATA` request fetches)
  - Goal: M4.40 showed that the router's kind-`0x40` request fetches the parcel's section-4 record (signposts: `0=POZNAN:KALISZ:(36):RAWICZ`), that header word 6/7 are the name offset/length and that the reply points at word 9 (C-5921, C-5925). The router consumer `0x00422eac` reads `w[k+15]` (gate `& 0x0f00 == 0x0900`), `w[k+7]`, `w[k+6] = d` and `w[k+d]`, with `k` from `0x00424464(19, …)`, which reads the renderer's section-1 buffer (`*0xe8f604` slot table). Map the section-4 entry layout from word 9 and the source of `k`.
  - Precheck: `python3 tools/datask_req_l3.py request archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --position 51.70,17.45 0xa6bed6ee:0:0x40` reads `pos 0x113ca000` (section 4); `python3 tools/sh4dis.py archive/head256.img Navi.exe --image-start 0x200200 --va 0x004240d8 --count 8` loads `0x00e8f604`.
  - Scope: EU2011; the section-4 level-1 records of `B48R058R` (1,382 zlib records) and `B30R058R` (8); `0x00424464` and its callees (11 functions); the section-1 point words that carry a section-4 index (hypothesis: a segment whose previous `y` has `0x1000` has an extra word; on `B30R058R` the 13 such words are 11/35/59, i.e. 24-word steps from word 11, all in parcels that have a section-4 record — scratch observation, not a claim).
  - Input: EXP-2026-11-20-M4.40-request-kinds, `tools/rgd_reply_l3.py` (`walk --section 4 --k K`), `tools/datask_req_l3.py`, `tools/section4.py`, `tools/ze0-viewer/tools_ze0/fa_encode.py` (`parse_record` point grammar), `docs/format/map-tiles.md` §Section 4 grammar.
  - Done when: an EXP gives the section-4 entry layout (offset, width, meaning or `unknown`) with the reading VA for each field `0x00422eac` touches, `k` derived from a section-1 record by the real `0x00424464` on one factory parcel (not chosen by the gate), and a negative control (a `k` from another parcel fails); `docs/format/map-tiles.md` §Section 4 grammar updated.
  - Stop: if no section-4 record of the two tiles has an entry that clears the `0x0900` gate, record the census and the gate's selection rule and stop.
  - Falsifier: the `k` that `0x00424464` returns on a factory parcel does not land on a section-4 entry start.
  - Claims: C-6030–C-6039

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

- [ ] **M4.57 — Polish voice: can the 2011 `Speech.exe` use the `SPEECH/` set of the EU 2014 card?**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M1.37 helps for `Speech.exe`)
  - Goal: EU 2011 ships 7 `SPEECH/` languages, EU 2014 adds nine including `PL` (C-2495). Find out whether the language files (VR, TTS, GID) changed format between the cards and how the 2011 firmware picks a language (the `DRSTR` `0x18c` code, C-2496, and the language list in the UI).
  - Precheck: both roots have `SPEECH/`; `python3 tools/diff_years.py` lists the language sets.
  - Scope: offline: headers and sizes of one language present on both cards (e.g. `EN`), byte-compared 2011 vs 2014; the SVOX/GID version fields; strings in `Speech.exe`/`SpeechCC.dll` that name languages. No card build.
  - Done when: an EXP says `same format` / `different` / `unknown` per file kind with the differing fields, and where the 2011 build's language list lives.
  - Claims: C-6320–C-6329
  - Step: tooling

- [x] **M4.58 — Skins: where they live and the `.skn` format (`ReleaseMain.skn`, the TFAT16 volume, `OPNG/`, ROM PNGs)**
  - Status: done · Owner: task/m4.58-skins-tfat16 · Critical: no · Pair: solo
  - Depends: — (M1.36b helps: the atlas lists `FILESentry` files per image)
  - Goal: Marek wants to change the unit's look. Three places hold skin data and none is decoded: `ReleaseMain.skn` (8,224 B, the only `FILESentry` of ROM A, C-3522) loaded by `multiskin.dll` (`Multiskin.Loader`), the TFAT16 volume at card offset `0x1C8400400` ("skin data", C-166, contents never listed), and PNG assets in ROM A (~`0x00df0000`) and `OPNG/`. Say which file decides what is drawn and what a skin id selects (`CApi_GetSkinID`/`SetSkinID`/`IsAvailableSpecifiedSkin` in `commondll.dll`).
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 files --extract <dir>` writes `ReleaseMain.skn`; the TFAT16 boot sector is at `0x1C8400400` of the full image (`7z l` or `mtools` on a slice lists it; this needs the full EU2011 image, not IMG256).
  - Scope: offline, EU2011 first, then the same three places on US2011/EU2014/EU2016 (sizes and hashes only). Output `docs/format/skins.md`: file list of the TFAT16 volume with types, the `.skn` layout (header, records, what they reference), how `multiskin.dll` finds its inputs (strings + imports), the count of embedded PNGs and how they are indexed. No card is built.
  - Hints: `.skn` is small, so it is an index/manifest rather than pixels; look for names or resource ids that match PNG entries. Compare `ReleaseMain.skn` with build B's `UpdateNK.skn` (compressed `FILESentry`, decode with `tools/nk_decomp.py files`): two samples of one format.
  - Done when: `docs/format/skins.md` exists with the TFAT16 listing (count, total bytes), a field table for `.skn` with every byte range `known`/`unknown`, and the answer "a skin is selected by … and its images come from …" with evidence status per sentence.
  - Stop: if the TFAT16 volume holds no skin files, record its real contents and correct C-166.
  - Claims: C-6500–C-6509
  - Step: tooling
  - Result: EXP-2026-11-21-M4.58-skins-tfat16 (C-6500–C-6509); docs/format/skins.md lists TFAT16 (3070 entries, 3066 placeholders, 1 real .skn) and the .skn field table; skin id 1..4 -> \SystemSD2\SkinChange\001..004\Substance.skn; gate 4 pass 0 fail

- [ ] **M4.59 — One changed image on the screen: the smallest skin edit that passes the checks**
  - Status: blocked · Owner: — · Critical: no · Pair: required
  - Depends: M4.58 (where the image is and what indexes it); M1.36b
  - Unblock: M4.58 done and it names one image whose bytes can be replaced in place (same size or with a known size field)
  - Goal: prove the mechanism before anyone designs a skin: replace one visible bitmap (same dimensions), fix every checksum on the way (ROM `SUM4` word sum, C-160, if the image is inside ROM A — both copies `0x200000` and `0x2000000`), and show the result is consistent offline.
  - Scope: a tool `tools/skin_patch.py` that patches a card image in place and reports changed ranges; `cardcheck --image` and `cerom.py` must still parse the ROM; an L3/L4 check if the loader can be run. Car test is M6 and belongs to Marek, after S0.
  - Done when: the patched image differs from factory only in the listed ranges, `SUM4` recomputed equals the stored value on both copies (negative control: without the fix it does not), and the patched PNG decodes.
  - Stop: if the image is in a compressed section or its size cannot stay equal, record why and stop.
  - Claims: C-6400–C-6409
  - Step: tooling

- [ ] **M4.60 — Sounds: inventory of every sound the unit plays and where its data is (beeps, chimes, voice prompts, TTS)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M4.57 covers the Polish language set; this is the map of all sound sources)
  - Goal: say what can be replaced as data and what is code. Candidates: `SPEECH/<lang>/` (per language VR, TTS, GID — the recorded guidance prompts are most likely the GID file), `BeepDrv.dll`/`MuteDrv.dll`/`DspDrv.dll` and `Audio.exe` (key beeps, chimes: samples in a module, or tones generated by the DSP / audio microcontroller?), WAV/PCM resources inside ROM A, and `CApi_GetCustomVoiceNo`/`SetCustomVoiceNo`/`GuidanceVoiceAtt` (a voice choice exists).
  - Precheck: `ls <ROOT>/SPEECH/*` lists three files per language; `python3 tools/cerom.py --image-start 0x200200 IMG256 imports BeepDrv.dll` prints its imports.
  - Scope: offline, EU2011 + US2011. Output `docs/format/sounds.md`: per source — location, size, container (RIFF/PCM/ADPCM/vendor), sample rate if readable, which module opens it. For GID: header fields, prompt count, whether prompts are indexed by id and stored as plain PCM/ADPCM (try to play one). Scan ROM A for `RIFF`/`WAVE` and count hits. No card is built.
  - Hints: the GID header carries a 16-digit date string (C-2496). SVOX TTS data is a vendor voice, not replaceable by a recording; recorded prompts are the realistic target for a custom voice.
  - Done when: `docs/format/sounds.md` lists every source with status, and states for the guidance prompts either a decoded sample (duration, codec) or the reason it could not be decoded; one line each: `replaceable as data: yes/no/unknown`.
  - Stop: if beeps turn out to be generated by the audio microcontroller (no sample data on the card), say so with the IOCTL/driver evidence and close that branch.
  - Claims: C-6570–C-6579
  - Step: tooling
- [x] **M4.61 — `COORD001` and `ADDRE` ids: is the low nibble `11xx` there too; make `coord.py` right for point ids**
  - Status: done · Owner: task/m4.61-point-ids · Critical: no · Pair: solo
  - Depends: M4.27 (done)
  - Goal: POINT copy-A words are not 1-unit coordinates (C-2679): the low nibble is `11xx` and the position continues in two 11-bit fields. `coord.py` and `refer.md` use `(x−32768)/192`, `(y−52742)/128` for `COORD001`, POINT and `ADDRE` ids alike. Check the nibble on every `COORD001` and `ADDRE` id of both cards, find the `ADDRE` counterpart of the fine fields (the `TT 40 XX YY` sub-cell tokens of C-1960–C-1969 are the candidate), and give `coord.py` one function for point ids that matches `point_census.fine_position`.
  - Precheck: `python3 tools/point_census.py refs --us DIR --eu DIR --refs docs/experiments/EXP-2026-11-08-M4.8b-poi-refs.tsv` prints `fine model holds`.
  - Scope: offline, EU2011 + US2011 `REFER001/COORD001`, `ADDRE0nn`; `tools/coord.py`. No firmware work (M3.34).
  - Input: EXP-2026-11-20-M4.27-point-census-fine-position, `tools/point_census.py` (`packed_units`, `fine_position`, `encode_position`), `docs/format/refer.md` (ADDRE sections), M4.19 EXP.
  - Done when: an EXP gives the low-nibble census of `COORD001` and `ADDRE` ids on both cards; `coord.py` has a point-id decode/encode with a selftest against `point_census`; `refer.md` says which files use the nibble form; for `ADDRE` either the fine field is named with a join against POINT records of the same address or the EXP says it is absent.
  - Stop: one session.
  - Claims: C-6560–C-6569
  - Step: P4
  - Result: EXP-2026-11-22-M4.61-point-ids; COORD001 132/132 + 44/44 11xx, ADDRE mixed per shard (EU 16.5M/17.4M, US 32.7M/33.0M); plain decode in-box, stripped out -> nibble is position, POINT-only marker; ADDRE fine field absent; coord.py point-id decode/encode, 15+22+33 selftest checks

- [ ] **M4.62 — TMC `0x14f4`: the dynamic tag writer (M4.51's continuation) and M4.49's truthful Unblock**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P3
  - Depends: M4.53 (done — the `0x14f4` file half: it reads `REFER001` POINT/ADDRE/INTER by its sub word, C-5680), M4.51 (blocked — the **negative static** census; read its Result first, this task does the dynamic half it could not do offline).
  - Goal: M4.49 blocks with "no link-group signature in the TMC data-layer subtree", and its `Unblock: M4.51` points at a task that has since blocked too. M4.51's Result closed the static question negatively: `0x14f4` has **no static sender** — the only send wrapper has 25 callers, each with one id literal, and none is `0x14f4`; the request is built at run time. M4.53 then closed the file half. So the whole chain M4.49 → M4.51 → M4.53 now ends in a `blocked`→`blocked`→`done` that can never re-open by rule 15, and the one open question is narrow and dynamic: which code writes the tag word of a request to `0x14f4` at run time, and what buffer it then fills. This task answers that or records it as unreachable, so M4.49 gets a `Unblock:` that names a merge that can actually happen (this task) instead of a dead token.
  - Precheck: `python3 tools/tmc_req_l3.py --selftest` passes; `python3 tools/rdstm_reader_scan.py archive/head256.img --const 0x14f4` prints its 7 data-layer users (the negative census M4.51 quotes — do not re-run the static literal scan as work); a `tools/read_watch_l3.py` run over the `OSM_TaskSend` wrapper path records the request tag word (offset `+8`) for a synthetic `0x14f4` call; quote the value, and if the run cannot write the tag that is the finding, not a failure.
  - Scope: EU2011 `Navi.exe` and the DLLs it imports; **dynamic half only**. (1) On the `OSM_TaskSend` wrapper path M4.51 named, find where the tag word (`u16` at request `+8`) is written from a computed value rather than a literal, and name the input it derives from (a caller context field, a table entry, a scaled constant); (2) follow the sender's buffer word to the buffer the `0x14f4` completion fills; (3) one L3 run with a read watch on `+8`, with `0x14e4` as the control. Excludes the static-literal census (M4.51 did it, negative — do not repeat), the RDSTM record grammar (M4.1/M4.2), and `RDSTM001.DAT` (M4.53 proved `0x14f4` does not read it).
  - Input: M4.51's Result and negative census (`tools/rdstm_reader_scan.py`, C-5404–C-5408), EXP-2026-11-20-M4.53-tmc-14f4-l3 (C-5680), `tools/tmc_req_l3.py`, `tools/read_watch_l3.py`, `tools/callgraph.py rank`, `tools/sh4dis.py`, `tools/tmc_reception.py`, `docs/format/rdstm.md`, EU card `105e2032…76307`.
  - Done when: an EXP names the writer of the `+8` tag word on the `OSM_TaskSend` wrapper path (its VA, the instruction that stores `0x14f4`, and the input it derives it from), or closes the question as "no reachable writer in EU2011 `Navi.exe`" with the dynamic run that shows the tag is never set to `0x14f4`; with one control that an unrelated tag (`0x14e4`) is written by the same path; **and** the same PR re-opens M4.49 under rule 15 with its `Unblock:` re-worded to what the EXP proves (this task done, or M8.E4 if the writer is L4-only) — M4.49 must not keep waiting on M4.51.
  - Stop: one session. If `+8` is written from a value only the full system produces (a DLL state object, an L4-only path), record the writer chain to that object, name it and its producer, and stop `blocked` on M8.E4 — that is the honest close for M4.49.
  - Falsifier: a static `0x14f4` literal that M4.51's census missed (then M4.51's negative is retracted, not this task built on it), or `+8` proven equal to a value `0x14e4` also writes with no branch on it (then `0x14f4` is a dead alias and M4.49 is retired, not unblocked).
  - Claims: C-6620–C-6629

- [x] **M4.63 — KIWI (`kiwiread`) jako wzorzec: zmapować struktury KIWI/KWI na rekordy naszej karty**
  - Status: done · Owner: task/m4.63-kiwi-map · Critical: no · Pair: solo
  - Depends: — (źródło zewnętrzne; host `github.com/jharg/kiwiread` dozwolony, klonuje się z sandboxa)
  - Goal: `jharg/kiwiread` (GPL-3, C, 2014) czyta format KIWI (`ALLDATA.KWI`/`LOADING.KWI` z samochodowych DVD nawigacji, np. Audi) i nazywa pola po numerach rozdziałów specyfikacji KIWI (np. „6.1.1 Level Management Record”, „7.2.1 Road Distribution Header”). Nasze rekordy (parcela, katalog poziomu 1, linki RDSTM, POINT, LCTBL) używają tych samych pojęć bez nazw. Zadanie sprawdza, które struktury KIWI mają odpowiednik w bajtach karty ZE0 i w czytnikach firmware, tak żeby nazwy i układ pól ze specyfikacji KIWI mogły trafić do `docs/format/` — albo żeby zamknąć ten trop jako „tylko wspólne pojęcia, inny format”.
  - Precheck: `git clone --depth 1 https://github.com/jharg/kiwiread` działa (commit `74741c5b`); `python3 tools/parcel_census.py --help` i `python3 tools/rdstm_record.py --help` działają; obraz US/EU z rule 11 pobrany. Jeśli pierwsza struktura z listy niżej (nagłówek wolumenu `datavol_t` / katalog z 4-znakowymi magikami i `offset*2+0x800`) nie ma żadnego kandydata w karcie, to jest wynik (negatywny), nie porażka.
  - Scope: tylko porównanie struktur. (1) Wypisać struktury z `kiwiread.c` z ich rozmiarem, kolejnością bajtów (kiwiread robi `swapw` — KIWI jest big-endian, jak nasze rekordy) i numerem rozdziału KIWI: `datavol_t`, katalog `dde[]` (magik 4 B, `offset` w słowach, baza `0x800`, rozmiar sektora `SWS`), `pdmdh_t` (nagłówek zarządzania danymi parceli: ramka lat/lng, `lmr_sz`/`bsmr_sz`/`bmr_sz`, `nlmr`/`nbsmr`), `lmr_t` (Level Management Record), `roadhdr_t`/`dcmr_t`/`multilink_t` (Road Distribution Header, multilinki, kształty/węzły), PID i kodowanie współrzędnych (`geo_secs`); (2) dla każdej porównać z naszym odpowiednikiem: `docs/format/rdstm.md` + `tools/rdstm_record.py`/`rdstm_links.py`, POINT (`tools/point_census.py`), LCTBL (`tools/lctbl_records.py`), parcele/poziomy (`tools/parcel_census.py`, `docs/format/map-tiles.md`, `coord-zcode-icode.md`), i z walkerem w firmware tam, gdzie jest znany (M3); (3) jedno sprawdzenie na bajtach karty dla każdej pary oznaczonej „pasuje” (pole, offset, wartość). Wyklucza: pisanie czytnika KIWI w repo, kopiowanie kodu GPL (tylko link i nazwy pól z cytowaniem), samą specyfikację KIWI z kiwi-w.org poza tym, co cytuje kiwiread.
  - Input: <https://github.com/jharg/kiwiread> (`kiwiread.c`, `osm.c`), `docs/research/sources.md` (wpis kiwiread), `docs/format/{rdstm,map-tiles,coord-zcode-icode,refer,cmp-ind}.md`, `tools/parcel_census.py`, `tools/rdstm_record.py`, `tools/point_census.py`, `tools/lctbl_records.py`, `tools/callgraph.py`, obraz US (`53342430…c5383`) lub EU (`105e2032…76307`).
  - Done when: EXP `EXP-YYYY-MM-DD-M4.63-kiwi-map.md` z tabelą „struktura KIWI → nasz rekord / pole / offset / werdykt (pasuje · częściowo · brak)” dla co najmniej sześciu struktur z listy, gdzie każde „pasuje” ma sprawdzenie na bajtach karty (plik, offset, wartość) i, jeśli znany, VA czytnika w firmware; claimy w bloku zadania; jeśli coś pasuje — nazwy pól KIWI dopisane do odpowiedniego `docs/format/*.md` z odnośnikiem do EXP; wpis kiwiread w `sources.md` zaktualizowany o wynik.
  - Stop: jedna sesja. Jeśli po trzech pierwszych strukturach (`datavol_t`, katalog, `pdmdh_t`) nic nie pasuje na bajtach, zamknąć jako negatywny wynik „wspólne pojęcia KIWI, inny kontener” z tymi trzema próbami i nie ciągnąć reszty.
  - Falsifier: pole oznaczone „pasuje”, którego wartość na drugiej karcie (US vs EU) lub w drugim kaflu nie zachowuje się jak pole KIWI (np. liczba poziomów, ramka lat/lng parceli) — wtedy dopasowanie jest przypadkowe.
  - Claims: C-8100–C-8109
  - Step: tooling
  - Result: EXP-2026-11-22-M4.63-kiwi-map; 0/4 header fits on 3 files, 8 structures mapped, negative verdict; gate 5/5

- [ ] **M4.64 — KIWI lineage in the firmware: every string and symbol that names a KIWI concept (parcel, level, block, Xanavi)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: Marek's hypothesis (2026-11-22): Clarion described the maps in the KIWI format, so a public specification could replace reverse engineering from zero. Clarion took over Xanavi, a KIWI-W member, and the ROM still says so: a raw scan of `IMG256` finds `xglXtpDrawXanaviCharacter`, `NOT XANAVI    : %d` and `MDP_pushRcvParcel` (`grep -a -c` below). Collect the full vocabulary and map each term to its module and function, so the other KIWI tasks start from names the firmware itself uses.
  - Precheck: `grep -a -c -e XANAVI -e Xanavi archive/head256.img` and `grep -a -c RcvParcel archive/head256.img` both print a number above 0 (measured 2026-11-22 on the pinned `IMG256`).
  - Scope: EU2011 ROM A/B/C, decompressed data sections included (`tools/ce_strfind.py`, both encodings). Vocabulary: KIWI terms from the chapter titles quoted in `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`) (parcel, level, block set, block, management record, distribution header, multilink, display class, minimum graphics, name data, route planning, route guidance, integrated information) plus `Xanavi`, `XTP`, `MDP`. For each hit: module, VA, referencing function (`tools/sh4xref.py`).
  - Input: `tools/ce_strfind.py`, `tools/sh4xref.py`, `tools/nk_decomp.py`, `docs/research/sources.md`.
  - Done when: an EXP table term → hits → module → referencing `fn` (pdata START), with the searched vocabulary and corpus size printed by the commands, and a verdict line per KIWI concept (`named in firmware` / `not named`); the start of `docs/format/kiwi-glossary.md` with those names; `docs/research/sources.md` kiwiread row updated.
  - Stop: one session.
  - Falsifier: the `Parcel`/`Xanavi` strings belong to a module unrelated to map data (a telematics or font module only) — then they are no evidence for the map format.
  - Claims: C-7630–C-7639

- [ ] **M4.65 — KIWI public sources: which specification versions exist, what each chapter covers, and what can be cited**
  - Status: open · Owner: — · Critical: no · Runner: non-Claude · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: The mapping tasks need the specification text, not only the field names a reader program quotes. Find the public KIWI documents (KIWI-W consortium format guides, the Japanese and ISO standards derived from it, academic descriptions, other open readers or converters) and record for each: version, date, where it is, licence, and its chapter list.
  - Precheck: `curl -sI https://www.kiwi-w.org/index_eng.html` answers from the runner's network (the Claude sandbox reaches only `files.viaaq.eu`, rule 12).
  - Scope: a source list and chapter index only; no specification text copied beyond short quotes; downloaded documents stay outside the repo with URL, date and SHA-256 recorded. Include web-archive copies if the consortium site is gone. List other open-source KIWI readers/writers with licence.
  - Input: `docs/research/sources.md`, `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`).
  - Done when: `docs/research/kiwi-sources.md` with one row per document (title, version, date, URL, SHA-256, licence, chapters) and one per tool; a paragraph saying which version the chapter numbers in `kiwiread.c` (1.2.x, 6.1.x, 7.2–7.4) match; `docs/research/sources.md` links it.
  - Stop: one session; if no specification is public, record where it was looked for and what the standards bodies sell.
  - Falsifier: the chapter numbers quoted by `kiwiread.c` match no public document (then its author worked from an unpublished one).
  - Claims: C-7640–C-7649

- [ ] **M4.66 — KIWI basic types against our bytes: the `SWS` size word, the `D` offset word and the 4-byte address `ssssssss ssssssss ssssssss DLnnnnnn`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: KIWI counts sizes in words and addresses data by sector + logical-sector fields (chapter 1.2.x as quoted in `kiwiread.c`). Our tile and container tables hold offsets and lengths whose unit was fitted from bytes. Test whether they are these KIWI types — a yes explains every offset table at once.
  - Precheck: `git clone --depth 1 https://github.com/jharg/kiwiread` works and `grep -n '1\.2\.' kiwiread/kiwiread.c` prints the type comments; `python3 tools/parcel_census.py --help` works.
  - Scope: the three types only. For each offset/size table already documented in `docs/format/map-tiles.md`, `cmp-ind.md` and `drstr.md` (tile level/box table, section directory, `.ind` table, `MMAIN001` level totals): state the documented unit and test the KIWI reading on EU2011 card tree (`ROOT`, Shared inputs) and the US card, counting fits and misfits.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/parcel_census.py`, `tools/cmpind.py`, `tools/mmain.py`, `docs/format/map-tiles.md`.
  - Done when: new `tools/kiwi_types.py` (decode the three types; `--selftest`; `census ROOT` prints fits/total per table) and an EXP table table → documented unit → KIWI type → fits/total on both cards; matching tables renamed in the format doc with the KIWI term in brackets.
  - Stop: one session; a table that fits neither reading is listed, not explained.
  - Falsifier: a table 'fits' on one card and fails on the other.
  - Claims: C-7650–C-7659

- [ ] **M4.67 — KIWI Level / Block Set / Block Management Records against `MMAIN001.DAT` and the tile level tables**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: KIWI describes the map pyramid in three record types (chapters 6.1.1, 6.1.2, 6.2.1 as named in `kiwiread.c`): level, block set, block. `MMAIN001.DAT` holds per-level totals and the tiles hold level/box tables. If they are the KIWI records, every unexplained field in them gets a name (display scale flags, parcel counts per block, latitude/longitude extents).
  - Precheck: `python3 tools/mmain.py --help` works; `grep -n '6\.1\.1\|6\.1\.2\|6\.2\.1' kiwiread/kiwiread.c` prints the three record comments.
  - Scope: field-by-field comparison: record size, field order, units; one numeric test per field on EU2011 card tree (`ROOT`, Shared inputs) and the US card (e.g. block counts multiply to the tile count, extents equal the tile frame from `tools/mesh_grid.py`).
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/mmain.py`, `tools/parcel_census.py`, `tools/mesh_grid.py`, `docs/format/drstr.md`, `docs/format/map-tiles.md`.
  - Done when: an EXP table KIWI field → our file/offset → test → pass/fail on EU and US, and the verdict per record (`same record` / `same idea, other layout` / `absent`); passing fields added to the format docs under their KIWI names.
  - Stop: one session.
  - Falsifier: a field passes only because its value is 0 or 1 on every sample (no information) — count such fields separately.
  - Claims: C-7660–C-7669

- [ ] **M4.68 — KIWI Parcel ID and coordinates against tile names and `coord.py` (normalised units, parcel division per level)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: KIWI gives every parcel an ID and stores positions as normalised offsets inside the parcel. Our tile names (`BxxRyyyR`), the level/box grid and the POI coordinate words were all derived by fitting. Test the KIWI rules: do they predict our grid sizes per level and the `11xx` nibble / fine-word split of point coordinates?
  - Precheck: `python3 tools/coord.py --help` and `python3 tools/mesh_grid.py --help` work; `grep -n '1\.2\.13' kiwiread/kiwiread.c` prints the Parcel ID comment.
  - Scope: arithmetic only: KIWI parcel size per level and coordinate resolution, compared with the measured grid (`docs/format/coord-zcode-icode.md`, M4.27, M4.61) on EU and US; includes the still-open POI latitude residual of M4.28 as a test case.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/coord.py`, `tools/mesh_grid.py`, `docs/format/coord-zcode-icode.md`, EXP-2026-11-20-M4.27-point-census-fine-position.
  - Done when: an EXP with the KIWI rule, our measured rule, and the difference per level (from `tools/mesh_grid.py`/`tools/coord.py` output); verdict; if the KIWI rule explains the M4.28 residual, the corrected formula as a patch to `tools/coord.py` with its selftest.
  - Stop: one session.
  - Falsifier: the KIWI parcel sizes are not an integer multiple or divisor of ours at any level.
  - Claims: C-7670–C-7679

- [ ] **M4.69 — KIWI Road Data Frame (chapter 7.2) against tile section 1: distribution header, display classes, multilink header**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P1
  - Depends: —
  - Goal: Section 1 of a tile carries the drawn roads; our writer uses 'provisional classes' because the class field is fitted. KIWI's road frame has a distribution header, display-class management records and multilinks with typed attributes. Test the layout on real section-1 bytes; a match names the road class codes and the attribute bits.
  - Precheck: `python3 tools/tilewriter.py --help` and `python3 tools/s1_wide_dir.py --help` work; `grep -n '7\.2\.' kiwiread/kiwiread.c` prints the road-frame comments.
  - Scope: one level-1 tile of the EU card and one of the US card: header → display-class records → multilink header → shape points, each compared with our `0x2046` directory model; the `class_code` values of M4.17/M4.29 against KIWI's road type list.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/tilewriter.py`, `tools/s1_wide_dir.py`, `tools/road_class_probe.py`, `tools/tile_class_roundtrip.py`, `docs/format/map-tiles.md`.
  - Done when: an EXP table KIWI structure → our structure → byte test → verdict, and for a match the road-type table (code → KIWI meaning → count on the EU card) in `docs/format/map-tiles.md`; `docs/research/reader-coverage.md` row 17 notes the result.
  - Stop: one session; stop after the multilink header if the display-class level already fails.
  - Falsifier: the KIWI field widths cannot tile our record without leftover bits.
  - Claims: C-7680–C-7689

- [ ] **M4.70 — KIWI Background Data Frame (chapter 7.3) against the odd-partner background records: polygons, shape classes, minimum graphics records**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: —
  - Goal: Water, forests and built-up areas are background data. KIWI stores them as typed units of 'minimum graphics records' (point, line, polygon; an 11-bit count of offset coordinates). Our tiles keep background in the odd partner record, mostly unexplained. Test the KIWI layout there.
  - Precheck: `grep -n '7\.3\.' kiwiread/kiwiread.c` prints the background comments; `grep -n -i 'background\|clarion_bg' docs/format/map-tiles.md tools/*.py` shows what we already decode.
  - Scope: one tile with a lake or a river on each card (pick by name from the name index); header size word, element unit table, type units, record flags, coordinate lists; closed-ring test for polygons.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/parcel_census.py`, `tools/tile_diff.py`, `docs/format/map-tiles.md`.
  - Done when: an EXP with the decoded structure of one background record (counts of points/lines/polygons per type code) or the offset where the KIWI layout stops fitting; if it fits, a type-code table (code → count → guessed meaning from one drawn example) in `docs/format/map-tiles.md`.
  - Stop: one session.
  - Falsifier: decoded polygons are not closed or leave the tile frame.
  - Claims: C-7690–C-7699

- [ ] **M4.71 — KIWI Name Data Frame (chapter 7.4) against tile names and section 4: name records, placement kinds, string encoding**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P2
  - Depends: —
  - Goal: KIWI name records carry an attribute header, a placement kind (along a line, at a point, symbol + string) and the string. Our section-4 writer leaves names empty (M5.65) and road-name placement is not understood. Test the KIWI layout on the name bytes we have.
  - Precheck: `grep -n '7\.4\.' kiwiread/kiwiread.c` prints the name-frame comments; `python3 tools/section4.py --help` and `python3 tools/name_strings.py --help` work.
  - Scope: one named road and one named town per card: header, record, placement variant, string bytes (encoding and terminator), link from the name to the road it labels.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/section4.py`, `tools/name_strings.py`, `tools/name_loaders.py`, `docs/format/map-tiles.md`.
  - Done when: an EXP table per record field with the byte test, the list of placement kinds seen with counts on one tile, and the verdict; a match is written into `docs/format/map-tiles.md` §section 4 and referenced from M5.65.
  - Stop: one session.
  - Falsifier: the decoded strings are not the names `tools/name_strings.py` already extracts from the same tile.
  - Claims: C-7700–C-7709

- [ ] **M4.72 — KIWI route-planning data against tile section 2 and `LEV3456R`: nodes, links, costs, upper-level links**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P3
  - Depends: —
  - Goal: The routing graph is the longest blocked chain on the board (M4.24, M4.40, M4.55, M5.57): section 2 framing is known, attributes are not. KIWI defines route-planning records (node, link, link cost, regulation, correspondence to the upper level). `kiwiread` does not parse them, so this task works from the specification index of M4.65 if present, else from the concepts alone.
  - Precheck: `python3 tools/tile_graph_roundtrip.py --help` works; `grep -n -i 'route\|plan' kiwiread/kiwiread.c` shows what the reader names (little — say so).
  - Scope: compare record kinds and field counts of KIWI route planning with our section-2 kinds (`0x2046`/`0x3e4`, even/odd records) and with the levels 3–6 file; one numeric test per proposed field (link length against geometry length, node degree against edge entries, level-up pointer against `LEV3456R` ids).
  - Input: `docs/research/kiwi-sources.md` (M4.65) if merged, `tools/tile_graph_roundtrip.py`, `tools/route_link_join.py`, `tools/lev3456.py`, EXPs of M4.24 and M4.40.
  - Done when: an EXP table KIWI route record → our record → test → verdict; every confirmed field written into `docs/format/map-tiles.md` and named in the `Unblock` notes of M4.40/M5.57 through `board.py field`.
  - Stop: one session; without the specification text, stop at the concept table and say which chapter is needed.
  - Falsifier: a proposed 'link length' field does not correlate with geometry length over one tile (state r and n from a command).
  - Claims: C-7710–C-7719

- [ ] **M4.73 — KIWI route-guidance data against tile section 4 (guidance) and `INTER`/`FRWAY`: intersection names, signposts, lane data**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P3
  - Depends: —
  - Goal: M4.56 reads the guidance grammar from the router's consumer. KIWI has a route-guidance frame (intersection, direction signs, road names for announcements). Check whether its record list predicts the fields M4.56 looks for and the content of `INTER0nn`/`FRWAY0nn`.
  - Precheck: `python3 tools/inter_table.py --help` works; M4.56's block names the consumer VA.
  - Scope: concept and layout comparison on one motorway junction of the EU card (an exit with a signpost text): which file holds the text, how it is tied to the link.
  - Input: `docs/research/kiwi-sources.md` if merged, `tools/inter_table.py`, `tools/section4.py`, `docs/format/refer.md`.
  - Done when: an EXP with the junction's records located in our files, the KIWI record each resembles, and a verdict; findings appended to M4.56 with `board.py field M4.56 Input … --append`.
  - Stop: one session.
  - Falsifier: the signpost text is found in no map file (then it is composed from road names at run time).
  - Claims: C-7720–C-7729

- [ ] **M4.74 — KIWI index data against `REFER001`: address, POI and category indexes (`POINT`, `ADDRE`, `ZCODE`, `ICODE`, `COORD`)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: The search database is the P4 step and the least decoded family (four readers unlocated or blocked). KIWI defines index data for address and facility search. Compare its structure list with the `REFER001` families: tries, leaf pages, coordinate tables, category lists.
  - Precheck: `python3 tools/point_census.py --help` and `python3 tools/addre.py --help` work.
  - Scope: structure-level comparison plus one byte test per family where a KIWI layout is available: tree node format, record id width, how a record points to a parcel.
  - Input: `docs/research/kiwi-sources.md` if merged, `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/point_census.py`, `tools/addre.py`, `tools/coord_zcode_icode.py`.
  - Done when: an EXP table family → KIWI index structure → test → verdict, and a list of fields this explains that `docs/format/refer.md` marks unknown.
  - Stop: one session.
  - Falsifier: KIWI's index is one container while ours is five unrelated files with different page formats.
  - Claims: C-7730–C-7739

- [ ] **M4.75 — KIWI character codes against our strings: which code set and which string form do map names use**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P2
  - Depends: —
  - Goal: KIWI fixes how strings are stored (code set identifiers, length forms). `LCTBL` strings, `POINT` names (byte order still open in M3.11b) and tile names each have their own decoder here. One KIWI rule might cover all three and settle Polish letters.
  - Precheck: `python3 tools/lctbl_string_decode.py --help` and `python3 tools/point_byteorder_l3.py --help` work.
  - Scope: the string forms in `kiwiread.c` (name record strings) against the three decoders; test words with non-ASCII letters from the EU card (German umlauts, the Polish towns of the four Poland tiles).
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `tools/lctbl_string_decode.py`, `tools/name_strings.py`, `tools/point_name_accessor.py`, the M4.13 record in `docs/research/todo-history-2026-11-09.md`.
  - Done when: an EXP table string family → length form → code set → sample → decodes identically under the KIWI rule (yes/no); a common decoder proposed if all three agree.
  - Stop: one session.
  - Falsifier: the same letter has different byte values in two families.
  - Claims: C-7740–C-7749

- [ ] **M4.76 — `kiwiread`'s OSM exporter as a class table seed: KIWI road and background types → OSM tags, inverted for our compiler**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P1
  - Depends: M4.69
  - Goal: `kiwiread` ships `osm.c`, which writes KIWI data as OSM. Its type → tag choices, inverted, are a first OSM → Clarion class table (M5.3) — valid only for the codes M4.69 confirmed on our card.
  - Precheck: `grep -c highway kiwiread/osm.c` prints a number above 0 and M4.69's EXP has the road-type table.
  - Scope: a table only: KIWI/Clarion code → OSM tag (as read from `osm.c`, cited by line) → inverse rule with a tie-break; codes not seen on the EU card are marked unused. No code copied.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), M4.69's EXP, `tools/roadclass_v0.py`, `docs/research/osm-pipeline.md`.
  - Done when: `profiles/` or `docs/research/osm-pipeline.md` gains the table; `python3 tools/roadclass_v0.py --selftest` still passes and a new check maps ten OSM `highway` values to codes that occur on the EU card (count from `tools/road_class_probe.py`).
  - Stop: one session.
  - Falsifier: more than half of the codes in the inverse table do not occur in any factory tile.
  - Claims: C-7750–C-7759

- [ ] **M4.77 — A real KIWI disc image as a control: run `kiwiread` on it and on our card**
  - Status: open · Owner: — · Critical: no · Runner: non-Claude · Pair: solo
  - Step: tooling
  - Depends: M4.65
  - Goal: A mapping claim is stronger with a positive control: the reader on a real KIWI volume, the same reader on our files, and the point where they part. Needs a lawfully held KIWI DVD image (`ALLDATA.KWI`), which the sandbox cannot fetch.
  - Precheck: the runner has such a file; `make` in the `kiwiread` checkout builds.
  - Scope: run `kiwiread` on the KIWI volume (positive control) and on `MMAIN001.DAT` plus one tile of our card (expected to fail — record where); nothing from the disc enters the repo, only its SHA-256, volume label and structure counts.
  - Input: `jharg/kiwiread` (GPL-3; link and field names only, never its code; commit in `docs/research/sources.md`), `docs/research/kiwi-sources.md`.
  - Done when: an EXP with the control output summary (levels, block sets, parcels decoded), the first structure at which our files stop parsing, and what that says about container vs content.
  - Stop: one session; without a lawful image, blocked with the list of where one can be obtained.
  - Falsifier: `kiwiread` parses our tile without error (then our container is KIWI and M4.66–M4.71 collapse into using it as an oracle).
  - Claims: C-7760–C-7769

- [ ] **M4.78 — KIWI verdict and plan: one page that says what the format buys us, and renames our fields**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M4.63, M4.64, M4.66, M4.67, M4.69
  - Goal: Close the loop for Marek's question 'is KIWI a shortcut?': gather the verdicts, decide per file family whether to adopt KIWI names and layouts, and turn each confirmed match into writer or reader work.
  - Precheck: the five EXP records exist on `main` (`ls docs/experiments | grep -c -e M4.63 -e M4.64 -e M4.66 -e M4.67 -e M4.69` prints at least 5).
  - Scope: `docs/format/kiwi-glossary.md` completed: KIWI term → our name → file/offset → status; a decision table per family (adopt / partial / unrelated); follow-up tasks added with `board.py add-task` for each adopted structure (a clean-room decoder in `tools/`, never GPL code).
  - Input: the EXPs of M4.63–M4.75, `docs/format/kiwi-glossary.md`.
  - Done when: the glossary page and decision table are on `main`, `docs/format/*.md` use the adopted names, and `python3 tools/map_signals.py` is quoted before and after (the `tile_bytes` number moves only if a decoder landed).
  - Stop: one session.
  - Falsifier: every family ends as 'unrelated' (then the page records the negative with its controls and the lead is closed in Retired leads).
  - Claims: C-7770–C-7779

- [x] **M4.79 — `ZCODE0nn`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.79-zcode-decode · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: Row 8 of `docs/research/reader-coverage.md` says the `ZCODE0nn` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'ZCODE' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/zcode_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/zcode_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-7800–C-7809
  - Result: EXP-2026-11-22-M4.79-zcode-decode; 33/33 EU shards censused (Form A 2, Form B 31), 96.45% of bytes explained, min 67.7% (ZCODE015); US has 0 ZCODE; Form-B header at 0x1100 + base 0x1204+off*2 verified

- [x] **M4.80 — `ICODE001`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.80-icode-decode · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: Row 9 of `docs/research/reader-coverage.md` says the `ICODE001` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'ICODE' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/icode_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/icode_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-7810–C-7819
  - Result: EXP-2026-11-22-M4.80-icode-census; EU 110597896/111378432 B 99.299%, US 6059118/6071808 B 99.791%, 8 EU chains, negative control 99.791%->49.905%

- [x] **M4.81 — `INTER0nn`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.81-inter-decode · Critical: no · Pair: solo
  - Step: P3
  - Depends: —
  - Goal: Row 12 of `docs/research/reader-coverage.md` says the `INTER0nn` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'INTER' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/inter_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/inter_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-7820–C-7829
  - Result: EXP-2026-11-22-M4.81-inter-decode; inter_decode tool+census, 44/44 shards, 88.301% explained, C-7820-C-7829

- [x] **M4.82 — `FRWAY0nn`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.82-frway-decode · Critical: no · Pair: solo
  - Step: P3
  - Depends: —
  - Goal: Row 13 of `docs/research/reader-coverage.md` says the `FRWAY0nn` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'FRWAY' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/frway_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/frway_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-7830–C-7839
  - Result: EXP-2026-11-22-M4.82-frway-decode (C-7830-C-7839); EU 26/33 99.56%, US 11/33 99.90%; 16/16 selftest

- [x] **M4.83 — `ICADM0nn`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.83-icadm-decode · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: Row 14 of `docs/research/reader-coverage.md` says the `ICADM0nn` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'ICADM' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/icadm_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/icadm_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-8360–C-8369 (C-7840–C-7849 taken by M4.84)
  - Result: EXP-2026-11-22-M4.83-icadm-decode; EU 88.98% / US 98.06% explained; claims C-8360-C-8369 (C-7840-C-7849 taken by M4.84)

- [x] **M4.84 — `ZIPFR001`: make the field decode reproducible (tool, census on both cards, firmware cross-check)**
  - Status: done · Owner: task/m4.84-zipfr-decode · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: Row 15 of `docs/research/reader-coverage.md` says the `ZIPFR001` decode is 'claim-only': it was done outside the repo and no committed tool reproduces it. Rule 16 wants a command. Write the decoder and count how much of the file it explains.
  - Precheck: `grep -n 'ZIPFR' docs/research/reader-coverage.md docs/format/refer.md docs/format/coord-zcode-icode.md` shows the current claims and the row still says `claim`; the file exists in the EU2011 card tree (`ROOT`, Shared inputs).
  - Scope: new `tools/zipfr_decode.py` with `--selftest` (synthetic) and `census ROOT`: header, tables, records, per-field value ranges, bytes explained / total; EU2011 and US2011. Where the opener or reader VA is known (matrix row), state which fields the firmware code confirms.
  - Input: `docs/format/refer.md`, `docs/format/coord-zcode-icode.md`, `tools/cmpind.py`, `tools/coord_zcode_icode.py`, the matrix row's EXPs.
  - Done when: `python3 tools/zipfr_decode.py census ROOT` prints records and bytes explained for every shard on both cards; `--selftest` is in `tools/selftest.py`; the matrix row's Offline cell changes from `claim` to `tool`; EXP + claims with one negative control (a mutated byte detected).
  - Stop: one session; unexplained fields are listed with their value histogram, not guessed.
  - Falsifier: the decode explains under half of the bytes of the file (then the claimed layout is wrong or partial — say which part).
  - Claims: C-7850–C-7859
  - Result: EXP-2026-11-22-M4.84-zipfr-decode; zipfr_decode census 100.0 % on EU2011/2014/2016, US2011 absent; selftest OK

- [ ] **M4.85 — `REFER002`, the EV layer: census of the 16 files and the charging-station record**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: `REFER002` holds the Leaf-specific data (charging stations with plug type and parking information). The matrix says 'EV schema xy/plug/parking undecoded'. For a Polish card this is the layer owners care about most after roads: chargers.
  - Precheck: `ls ROOT/REFER002 | wc -l` prints the file count and `grep -n REFER002 docs/format/refer.md` shows the current text.
  - Scope: EU2011 and US2011: per file the container kind (same page format as `POINT0nn`?), record count, and for the station file the fields position (same coding as POI positions, `tools/coord.py`), name, plug/operator codes. Check three stations against their known real-world location.
  - Input: `tools/point_census.py`, `tools/cmpind.py`, `tools/coord.py`, `docs/format/refer.md`.
  - Done when: new `tools/refer002_census.py` (`--selftest`, `census ROOT`) and an EXP with the per-file table and the station record layout (field, bits, evidence); `docs/format/refer.md` §REFER002 written; matrix row 24 updated.
  - Stop: one session; plug-type code meanings may stay open if the layout is done.
  - Falsifier: station positions decoded with the POI rule fall outside the card's coverage area.
  - Claims: C-7860–C-7869

- [x] **M4.86 — What is still unexplained in a factory tile: rank the unknown bytes of `B48R058R` by structure**
  - Status: done · Owner: task/m4.86-tile-unknown · Critical: no · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: `tools/map_signals.py` reports one of the three sample tiles far less explained than the others. Break its unexplained bytes down by level, record kind and directory, so the next format task takes the largest block instead of a guess.
  - Precheck: `python3 tools/map_signals.py --factory-root ROOT` prints the `tile_bytes` line with three percentages.
  - Scope: the tile named in that line with the lowest percentage; a table of unexplained ranges grouped by (level, even/odd record, section, directory kind), sorted by size, with the first bytes' shape (count words, offsets, coordinates?) described, not dumped.
  - Input: `tools/map_signals.py`, `tools/parcel_census.py`, `tools/ze0_tile_header.py`, `docs/format/map-tiles.md`.
  - Done when: `python3 tools/parcel_census.py … --unexplained` (or a new `tools/tile_unknown.py` with `--selftest`) prints the ranked table; the EXP names the top five blocks and the board task (existing or new via `board.py add-task`) that owns each.
  - Stop: one session.
  - Falsifier: the unexplained bytes are spread evenly in small gaps (padding) rather than in blocks.
  - Claims: C-7870–C-7879
  - Result: EXP-2026-11-22-M4.86-tile-unknown-ranking; 67,928,024 B ranked, residual 366,814 B -> M4.93

- [x] **M4.87 — Polish letters on the map: glyph coverage of the map font (`xglXtpDrawXanaviCharacter`)**
  - Status: done · Owner: task/m4.87-polish-glyphs · Critical: no · Pair: required
  - Step: P2
  - Depends: —
  - Goal: A Polish map needs ą ć ę ł ń ó ś ź ż drawn. M4.13 settled string storage; whether the renderer has the glyphs is a separate question. Find the font data the map text renderer uses and list the code points it can draw.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --image-start 0x200200 xglXtpDrawXanaviCharacter` prints the module; the M4.13 record in `docs/research/todo-history-2026-11-09.md` is read first.
  - Scope: EU2011: the renderer function (pdata START), the font resource (in ROM or on the card: `OPNG/`, a `.skn`, a font file), its code-point table; the 18 Polish letters (both cases) checked one by one; what the renderer does for a missing glyph.
  - Input: `tools/sh4xref.py`, `tools/skn_info.py`, `docs/format/assets.md`, `docs/format/skins.md`.
  - Done when: an EXP table letter → code point → glyph present (yes/no) → evidence, the fallback behaviour with its VA, and a recommendation for the compiler (keep / transliterate) recorded in `docs/research/osm-pipeline.md`.
  - Stop: one session.
  - Falsifier: the glyph table lists a letter as present but the Polish towns on the factory card are stored without diacritics (then data, not the font, is the limit — record it).
  - Claims: C-7880–C-7889
  - Result: EXP-2026-11-22-M4.87-polish-glyphs; C-7880-C-7889; 8/18 letters present (ĄąĆćĘęÓó), 10 absent; fallback 0x03451ede; recommendation in osm-pipeline.md; gate 5 pass/0 fail/0 skip

- [ ] **M4.88 — POI categories: the category code list, its names and icons (`BICON001`), as a table the compiler can target**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P4
  - Depends: —
  - Goal: To place OSM POIs we need the unit's category codes: which exist, what each is called in the menu, which icon it uses. Parts are known (103 icons in `BICON001`), no table joins them.
  - Precheck: `python3 tools/poi_icons.py --help` and `python3 tools/point_census.py --help` work.
  - Scope: EU2011 card: distinct category codes in `POINT0nn` with record counts, the icon index each maps to, and the category name (from the search menu strings in ROM A or from the name pages of the card). Ten codes checked against a known real place.
  - Input: `tools/point_census.py`, `tools/poi_icons.py`, `tools/ce_strfind.py`, `docs/format/refer.md`, `docs/format/assets.md`.
  - Done when: `docs/format/poi-categories.md` with the table (code, count, icon, name, evidence) generated by a command (`tools/poi_categories.py --selftest`, `table ROOT`); EXP + claims.
  - Stop: one session; names for rare categories may stay empty.
  - Falsifier: two different codes share every sampled real-world category (then the code is not a category).
  - Claims: C-7890–C-7899

- [ ] **M4.89 — Poland on the later cards as an oracle: do the 2014/2016 Poland tiles decode with the 2011 tools**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P2
  - Depends: —
  - Goal: The EU 2014 and 2016 cards belong to another unit generation, but if their map files keep the 2011 format, their Polish coverage is a factory-made answer sheet: Polish names, the country code in `LCTBL` (M5.64), road classes on Polish roads, POI categories.
  - Precheck: `python3 tools/fetch_image.py --image EU2014 -o PATH` verifies; `python3 tools/diff_years.py --help` works; EXP-2026-11-19-M4.41-diff-years is read first for what is already known.
  - Scope: per file family of the matrix: run the 2011 decoder on the EU2014 file covering Poland; verdict decodes / decodes with differences / different format; count Polish-named records; no 2014 bytes in the repo.
  - Input: `tools/diff_years.py`, `tools/diff_years_tiles.py`, `tools/parcel_census.py`, `tools/lctbl_records.py`, `tools/point_census.py`, `docs/research/image-versions.md`.
  - Done when: an EXP table family → verdict → Poland record count on EU2011 vs EU2014, and the three facts it settles for the compiler (at least the `LCTBL` country/table code used for Poland, quoted from a command); matrix column 'Cross-year' updated.
  - Stop: one session; a family whose container differs is listed as such, not converted.
  - Falsifier: the 2014 card has no more Polish detail than the 2011 card (same tile sizes for the Poland tiles).
  - Claims: C-7900–C-7909

- [ ] **M4.90 — Road numbers and shields: how the factory map stores `A4`, `E40`, `B6` and which shield the renderer draws**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P2
  - Depends: —
  - Goal: The first emulator screenshots show road shields. For Poland we need `A4`, `S8`, `DK94`, `E40` to appear correctly: find where a road's reference number lives, how the shield type is chosen, and which shield types exist.
  - Precheck: `python3 tools/name_strings.py --help` works and a motorway tile of the EU card contains a string like `A4` (count from the tool).
  - Scope: EU2011 card: the reference string's location (name frame vs a separate field), the shield-type field and its values with counts per country, the national/European distinction; the German set mapped to what Polish roads would use.
  - Input: `tools/name_strings.py`, `tools/section4.py`, `tools/tilewriter.py`, `docs/format/map-tiles.md`.
  - Done when: an EXP with the field layout and a shield-type table (value, count, example road), and a proposed mapping for Polish `ref` values in `docs/research/osm-pipeline.md`.
  - Stop: one session.
  - Falsifier: the shield type is derived from the road class alone (no separate field) — then say so with the class table.
  - Claims: C-7910–C-7919

- [x] **M4.91 — The opening picture: format of the image the launcher shows at start, decoded and re-encoded**
  - Status: done · Owner: task/m4.91-opening-picture · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: The launcher loads an opening image from the card before anything else (seen at L4 in EXP-2026-11-21-M8.C1b-hpb-dmac-model). It is the cheapest visible proof that a self-made card runs: a changed picture at power-on, in the emulator and in the car. M4.59 (skins) is blocked; this file is simpler.
  - Precheck: `python3 tools/ze0_sdhost.py --help` works and the M8.C1b EXP names the file and its size; `ls ROOT/OPNG` lists the candidates.
  - Scope: EU2011 and US2011: which file, header, pixel format (the size suggests raw 800 × 480 frames — test it), how many frames, any checksum; decode to PNG and encode back.
  - Input: `docs/format/assets.md` §OPNG, EXP-2026-11-21-M8.C1b-hpb-dmac-model, `tools/skn_info.py`.
  - Done when: new `tools/opng.py` (`--selftest`; `decode FILE -o PNG`, `encode PNG -o FILE`): decode → encode is byte-identical on the factory file of both cards (L2 round trip), and `docs/format/assets.md` describes the layout; the decoded picture stays out of the repo.
  - Stop: one session.
  - Falsifier: the decoded image is noise under every plausible pixel format (compressed or encrypted — record the entropy and stop).
  - Claims: C-8170–C-8179
  - Result: EXP-2026-11-22-M4.91-opening-picture (C-8170-C-8179); tools/opng.py --selftest 10/10, decode->encode byte-identical on EU+US factory files (sha256 + cmp); BASS container decoded; raw-pixel hypothesis refuted (entropy 5.2559, pixel grammar UNKNOWN)

- [ ] **M4.92 — Traffic for Poland: which countries and location tables does the EU 2011 `TMC/reception.dat` cover**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P3
  - Depends: —
  - Goal: `RDSTM001`/`LCTBL001` must be generated for Poland, but traffic also needs the receiver side: the list of countries, location-table numbers and service identifiers in `TMC/reception.dat`. If Poland is absent there, generated location data would never be asked for.
  - Precheck: `python3 tools/tmc_reception.py --help` works on `ROOT/TMC/reception.dat`.
  - Scope: EU2011 and EU2014: country codes, table numbers, services per country; whether Poland is present; what a Poland entry on the 2014 card looks like.
  - Input: `tools/tmc_reception.py`, `tools/tmc_fielddir.py`, `tools/lctbl_records.py`, `docs/format/rdstm.md`.
  - Done when: an EXP table country → location table → services for both cards, generated by one command, with the Poland row (present/absent) and its consequence written into `docs/research/data-coverage.md`.
  - Stop: one session.
  - Falsifier: the file lists services without any country or table field (then coverage is decided elsewhere — name where).
  - Claims: C-8180–C-8189

- [ ] **M4.93 — Section-4 wide rows: the `0x1146`–`0x1946` directories left unexplained by the `0x2046` row model**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P3
  - Depends: —
  - Goal: `tools/tile_unknown.py` shows that section 1's wide rows are already modelled by `s1_wide_dir.py` (M5.53/M5.54), but `B48R058R` still has 366,814 B in 36 gaps after that model. Every one is a section-4 level-1 `0x0009` place-name record in a `0x1146`–`0x1946` directory — the same wide-row family with a `0x1046` base that `s1_wide_dir.py` does not handle. Generalise the row model so those records have an owner instead of being copied verbatim.
  - Precheck: `python3 tools/tile_unknown.py /home/marek/projekty/leafre-work/m5.4/card-factory/MAPAL001/B48R058R.DAT --top 12` prints `still unexplained 366814 B in 36 ranges` (a byte count, not a line number).
  - Scope: EU2011 `B48R058R` section 4: 64 level-1 directories (30 `0x1046`, 13 `0x1146`, 6 `0x1246`, 6 `0x1346`, 3 `0x1446`, 2 `0x1546`, 1 `0x1646`, 2 `0x1746`, 1 `0x1946`) and the 36 residual gaps; no firmware run, no writer.
  - Input: `tools/s1_wide_dir.py`, `tools/tile_unknown.py`, `docs/format/map-tiles.md` §"Section 4, road names and streaming", EXP-2026-11-22-M4.86-tile-unknown-ranking.
  - Done when: a `--selftest`-covered tool (new `tools/section4_wide.py` or an extension of `s1_wide_dir.py`) parses every section-4 level-1 directory of `B48R058R` with size/record checks, and adding its spans to `tools/tile_unknown.py` drops the `still unexplained` figure to 0 B or prints a per-block shape for anything it cannot model; an EXP names the count and the record grammar.
  - Stop: one session.
  - Falsifier: the residual bytes are not wide-row records (no size/record rule fits) — then say so with the counted gaps and their shapes.
  - Claims: C-8310–C-8319

## M5 — OSM compiler vertical slice (Dolnośląskie)

Done: M5.0 (IMF v1 + `tools/imf_check.py`, EXP-44). See
`docs/research/osm-vertical-slice.md` and `profiles/dolnoslaskie-test.*`.

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

    `imf_check.py --assign-tiles` agrees.
  - Result: `tools/mesh_split.py` clips ways at cell borders with exact
    intersections and per-side nodes; `imf_check --assign-tiles` agrees
    (EXP-2026-11-06-M5.2-mesh-splitter).
  - Claims: C-1040–C-1049

- [ ] **M5.3 — OSM → Clarion road class/speed table**
  - Status: open · Owner: — · Critical: yes
  - Step: P2
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
  - Step: P2
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


- [x] **M5.12c — Every copy of the renamed POI name on the US card**
  - Status: done · Owner: — · Critical: yes
  - Step: P4
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
  - Result: EXP-2026-11-08-M5.12c-poi-copies (POINT pages, 131/136 renamed)
    + EXP-2026-11-20-M5.27-m5.12c-scan (uncompressed files, finished by M5.27):
    175 hits in the 132 uncompressed US files, none followed by `@`, no
    `HANA HEALTH` hit; 20 bare `CRAB ORCHARD` tile labels may still draw on
    the map, POI list/search read the POINT records. No search index holds
    the names, so no extra edit is needed. The 5 unfit records are M5.32.

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

- [ ] **M5.16 — `LEV3456R.DAT` generator: levels 3–6 from OSM (H11 G4)**
  - Status: blocked · Owner: task/m5.16-lev3456-generator · Critical: no
  - Step: P2
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

- [ ] **M5.18 — `POINT` and `ADDRE` writers, the two families Poland must generate (H11 G6)**
  - Status: open · Owner: — · Critical: yes
  - Step: P4
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

---


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

- [x] **M5.30 — One-variable OSM tile card via `imgpatch`/reconcile (1:1 diff, L1+L2)**
  - Status: done · Owner: task/m5.30-one-variable-card · Critical: no
  - Depends: M5.29, M5.13 (imgpatch), M5.20 (reconcile)
  - Goal: make the Poland compiler candidate card differ from factory only in changed tile/manifests clusters and their directory entries (same safety pattern as S1/S2).
  - Precheck: `imgpatch.py` and `mkcard.py` selftests pass; M5.29 produces changed tile + rebuilt manifests with known paths.
  - Scope: apply M5.29 output via `imgpatch.py` (preferred) or `mkcard --reconcile`; run diff-range proof (every diff range inside replaced files' clusters or 32-byte dir entries). No hardware.
  - Input: factory EU 2011 image, M5.29 outputs, `imgpatch.py`, `mkcard.py`, `cardcheck.py --image`.
  - Done when: `cardcheck.py --image` passes; EXP lists every diff range confined to intended files' clusters/dir entries; manifests touched only when required listed explicitly. Images outside repo.
  - Stop: if changed tile/manifests cannot fit existing chains and relocate/reconcile widens diff beyond changed files, record ranges and stop — do not claim one-variable.
  - Result: EXP-2026-11-19-M5.30-one-variable-card.md — allocator bound fixed (115,185 data clusters, last valid 115,186); one-variable card SHA-256 `b0faf119ee2ccfb3ce757bafa49ba7bdac6730d32c8ac97a2337fb18e3c33237`; `cardcheck --image` PASS; diff 586 ranges / 152,815 B, outside 0 with `--allow-metadata` / 9 (FAT/FSInfo) strict; L2 PASS on the result tree; `7z t` and `fsck.fat -n` accept the card; claims C-3060–C-3066.
  - Claims: C-3060–C-3069

- [x] **M5.34 — Put the OSM test road into a `0x2046` parcel so the factory-backed one-tile run completes (unblocks M5.29, PR #171)**
  - Status: done · Owner: task/m5.34-parcel · Critical: yes · **Runnable here** (2026-11-17: OSM API 200, Geofabrik 307, full EU card in `archive/sd-images/`; the `Runner: non-Claude` flag was a Claude-sandbox property, rule 12); the parcel census part needs no download
  - Depends: M5.22 (done: `PRESERVE_ONLY_DIR_KINDS`). **Was `M5.29 (blocked)`** — that made a deadlock: M5.34 is M5.29's `Unblock:`, so as written M5.34 waited on the very task it unblocks (SE 2026-11-17). The parcel census (Scope 1) needs no OSM extract and can run now.
  - Goal: PR #171 stopped because the test ways fell into directory `y=76 x=941` of `B48R058R`, kind `0x2146`, which `tilewriter` rightly refuses to mutate. That is a property of the chosen test geometry, not of the pipeline: the same tile has 30 `0x2046` directories (13 are `0x2146`; M5.4 spliced 18 *parcels* inside one `0x2046` directory) that M5.4 already splices with L2 PASS. Choose the corridor so that it lies inside one of them, and treat every non-`0x2046` directory as verbatim.
  - Precheck: `python3 tools/fetch_image.py --image EU2011 -o PATH` + `python3 tools/verify.py --image PATH` give the factory root (rule 11 — "EU2011 not available" was wrong, see EXP-2026-11-09-M5.29-factory-rerun); `python3 tools/tilewriter.py --selftest` 68/68.
  - Scope: (1) `tilewriter.py` (or a small `tools/parcel_census.py`) prints for a tile every directory `(y, x, kind, slots, bbox in WGS84)`; (2) `one_tile_pipeline.py --factory-root … --cell B48R058R --parcel Y,X` clips the OSM input to that parcel's bbox and fails early, with the kind named, when a way touches a preserve-only parcel; (3) the rerun and gate report. No change to how `0x2146` is handled.
  - Input: EXP-2026-11-08-M5.4-tile-splice (which `0x2046` directory it wrote and its L2 result), EXP-2026-11-08-M5.22 (slot-table model), `tools/mesh_grid.py`/`coord.py` (parcel ↔ coordinates), `profiles/dolnoslaskie-test.*`, branch `task/m5.29-factory-eu-rerun` (PR #171: the `--factory-root` mode).
  - Hints: take the parcel M5.4 used first — it is known to pass. If the committed OSM fixture has no way inside it, a two-node synthetic way with coordinates inside the bbox is a valid first run (state it as synthetic geometry on factory data); the real Dolnośląskie ways come second. If no `0x2046` parcel of `B48R058R` contains a drivable way, list the tiles of the profile by `0x2046` share and move the test cell.
  - Done when: M5.29's `Done when` is met on the factory root (`cardcheck` + applicable `l2check` pass, gate report per file), exactly one tile differs from factory and inside it only the chosen directory; PR #171 is merged or closed in favour of this PR; M5.29 → done, M5.30 open.
  - Stop: if every candidate parcel fails L2 for a reason other than the directory kind, record the first failing check and block on that.
  - Result: EXP-2026-11-17-M5.34-parcel. `tools/parcel_census.py` (new, `--selftest` 16/16) lists all 64 section-1 level-1 directories: 30 `0x2046` + 13 `0x2146` + 6 `0x2246` + 6 `0x2346` + 3 `0x2446` + 2 `0x2546` + 1 `0x2646` + 2 `0x2746` + 1 `0x2946`. `one_tile_pipeline.py` gained `--parcel` (directory bbox via `clarion_bg.parcel_geo`), real `--osm` in factory mode, a pre-write preserve-only refusal naming the kind, `--clip`, and tile/tree diff proofs (`--selftest` prints `selftest: OK (0 failure(s))`, 87 `ok` lines). Factory run into `(76,940)` `0x2046`: `cardcheck` PASS, targeted `l2check` PASS (`tiles=1`), exactly `MAPAL001/B48R058R.DAT` + `DRSTR001.DAT` differ (478 of 480 files compared are identical, no out-only or missing file), only section 1 / directory `(76,940)` changed. Negative control `(76,941)` `0x2146` refused before any write. C-3560–C-3569. PR #215.
  - Claims: C-3560–C-3569

- [ ] **M5.35 — One-command Poland card proof: `mkpoland` runs compiler → L1 → L2 → L3 gate and writes the evidence bundle**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M5.11, M5.30, M5.29 (gate report format), M9.60 (card gate, first slice; was M9.12, which waits on M9.31 → M9.41 and only adds the POI row — PO 2026-11-20)
  - Goal: every Poland milestone so far is a chain of manual commands in EXPs; a bench card needs one reproducible command that names the input OSM extract, writes the card, runs `cardcheck`/`l2check`/`l3check --card` and emits a machine-readable bundle. This is the L1→L2→L3 evidence path the PO prioritises, and it makes each L5 run one variable.
  - Precheck: `python3 tools/l2check.py --help | grep -- --cmp-limit` and `python3 tools/mkcard.py --selftest` pass; M5.30 produces a card that differs from factory only in expected clusters. If M5.11's compiler entry point is not yet stable, name the current one in the EXP and gate the wrapper on it.
  - Scope: new `tools/mkpoland.py` (`--selftest`, synthetic no-vendor fixture): `--osm EXTRACT --factory IMAGE -o OUT.img` calls the Poland compiler, `cardcheck --image`, `l2check --root` on the extracted tree, and `l3check --card` when a runnable target set exists; writes `bundle/manifest.json` (input/OSM SHA-256, tool versions, per-stage PASS/FAIL/SKIP/NOT_RUNNABLE, changed-cluster list) and `bundle/report.md`. Never promotes SKIP/BLOCKED to PASS (rule 13). Not: automatic car/bench execution.
  - Input: `M5.11` compiler CLI, `tools/mkcard.py`, `tools/cardcheck.py`, `tools/l2check.py`, `tools/l3check.py`, M5.29 EPX gate-report format, `profiles/dolnoslaskie*`.
  - Hints: reuse H27 `progress_schema` for status classes so the bundle feeds `progress_report.py`; the L3 stage must report `NOT_RUNNABLE` honestly on a host without the firmware image and never fabricate a verdict. The no-vendor CI path runs the synthetic fixture only.
  - Done when: one command produces a bundle on the committed synthetic fixture; on the factory EU image it produces a bundle whose L1/L2 stages pass and whose L3 stage names runnable/blocked targets; a selftest proves a forced L2 failure makes the command exit non-zero and the manifest records `FAIL`.
  - Stop: if M5.11's CLI is not yet callable as a library or command, deliver the stage runner + manifest with the compiler stage `NOT_IMPLEMENTED` and block on M5.11 naming its entry point.
  - Claims: C-3680–C-3689

- [x] **M5.37 — L2 golden for the route graph: tile section 2 must decode to the same node/link graph the writer emitted**
  - Status: done · Owner: task/m5.37-route-graph-golden · Critical: yes · Pair: required
  - Depends: M5.4 (tile splice, done), M5.23 (record fields, open — this task is the read-back side and may run on the fields M5.23 pins), M5.16 (which VA/section the router reads; this task checks the L2 model, not the firmware)
  - Goal: the map is also a router: `MAPAL001` tile section 2 is the routing graph (AGENTS: "Tile section 2 (router graph) copy — always preserved verbatim"), and no L2 check proves that a *generated* graph decodes back to the same edges. Without this, a card can render roads but route on a graph we never verified, and every gate is green. This is the L2 prerequisite for `M5.16`/`M4.39` ever becoming useful.
  - Precheck: `python3 tools/ze0-viewer/harness.py info <tile>` shows a non-zero section 2; `python3 tools/tile_diff.py --selftest` passes; confirm what is checked today: `grep -rn 'section 2\\|sec2\\|graph' tools/l2check.py tools/ze0-viewer/tools_ze0/clarion_tile.py` shows decode but no emitted-vs-decoded graph comparison.
  - Scope: `tools/l2check.py` (one check `tile_graph_roundtrip`) plus a synthetic fixture: emit a small edge set into a factory-shaped tile section 2, decode it, compare node/link counts and endpoint coordinates. Real-image variant on the M5.4 splice; preserve-only tiles must still report `preserved`, not `fail`. No new graph grammar claim.
  - Input: `tools/ze0-viewer/tools_ze0/clarion_tile.py`, `tools/tile_diff.py`, `tools/tilewriter.py`, M4.23/M4.24 section-2 grammar (partial), M5.4 EXP, M5.23 for the field layer.
  - Hints: the section-2 grammar is only partly decoded (M4.23 part b open), so compare at the level the writer round-trips today (node/link framing, coordinates) and mark the edge-attribute layer `UNKNOWN`; do not block the framing check on M4.24. A `_preserved` tile is a PASS only for the preservation property, never for "graph matches".
  - Done when: `tile_graph_roundtrip` reports PASS on the synthetic fixture and on the real splice, FAIL when one emitted link endpoint is moved, and `preserved` for an untouched tile; `python3 tools/selftest.py` passes; EXP states which attributes are compared and which are `UNKNOWN`.
  - Stop: if section 2 cannot be decoded for any edge (no grammar), report `BLOCKED — section-2 grammar unknown` naming M4.23/M4.24 and do not claim a graph check.
  - Falsifier: the check passes on a tile whose emitted graph has one fewer link, or a `_preserved` tile is reported as a graph match.
  - Claims: C-5160–C-5169 (was none yet; fresh block for this run)
  - Result: EXP-2026-11-19-M5.37-route-graph-golden — `tools/tile_graph_roundtrip.py` + `l2check --graph-tiles`: PASS on the synthetic fixture (2/2) and on the real `B48R058R` splice with 32 writer-emitted section-2 records (32/32, 73,384 others factory-identical); FAIL on a moved endpoint, a dropped link and an unclaimed change; `preserved` (73,416) for an untouched section 2; factory re-emit 67,674/69,345 records, 0 failures. Compared: parcel, nodes, links (id, direction), edge entries; `UNKNOWN`: w4, w5, class/cost words, countries, part b (C-5160–C-5166).

- [ ] **M5.57 — Section-2 writer: the full route graph of a generated tile from OSM (attributes, not only framing)**
  - Status: blocked · Owner: — · Critical: yes · Pair: required
  - Step: P2
  - Depends: M4.40 (section-2 grammar incl. part b), M5.37 (L2 graph round-trip, done), M4.39 (link key `(parcel, class & 0xf, w3 & 0x1fff)`, done), M5.23 (section-1 record fields)
  - Unblock: M4.40 (field table for part a and part b in `docs/format/map-tiles.md` with the reading VA per field)
  - Goal: a generated tile can render roads today but routes on a graph we never wrote: the writer emits section-2 framing (nodes, links, direction, M5.37) and keeps the rest factory/empty. Write every section-2 field from OSM so the router has the data it needs: one-way (`oneway`), road class (from the M5.36 class map), connectivity at shared nodes, and turn restrictions (`type=restriction`) where the grammar has a place for them.
  - Precheck: M4.40 is `done` and its field table lists part b with 0 unexplained bytes (or the unexplained ranges named); `python3 tools/tile_graph_roundtrip.py --selftest` passes; `python3 tools/l2check.py --help` shows `--graph-tiles`.
  - Scope: the section-2 emitter used by `tools/tilewriter.py` (new `tools/sec2_writer.py` if cleaner), EU2011 ZE0 X08-02-00 tiles, Dolnośląskie test bbox. Each OSM attribute maps to a named field or is listed `not representable`. No LEV3456R, no section 4 (names), no new grammar claims beyond M4.40.
  - Input: M4.40 EXP + `docs/format/map-tiles.md` §section 2, `tools/rd_restrictions.py`/`clarion_rd` (part-a layout), `tools/tile_graph_roundtrip.py`, M5.36 class map, M4.39 `tools/route_link_join.py`, M5.44 grid.
  - Hints: start from a factory tile: re-emit its section 2 from its own decoded graph and require byte identity (or list each differing range with the reason) before writing an OSM graph. Junctions: OSM ways share node ids, the tile shares `(x, y)`; keep both sides of a split way connected.
  - Done when: (1) factory `B48R058R` and one control tile re-emit section 2 byte-identically from the decoded graph (or the residue is enumerated); (2) an OSM-built tile passes `l2check --graph-tiles` with every edge attribute compared (none `UNKNOWN` that M4.40 decoded); (3) a mutant that flips one `oneway` FAILs the round-trip.
  - Stop: if factory re-emit is not byte-identical after two rounds, record the differing fields and stop; do not ship an approximate graph to a card.
  - Falsifier: the round-trip passes on a tile whose emitted graph has one link with reversed direction.
  - Claims: C-5850–C-5859

- [x] **M5.38 — The card ladder P0–P4: what a Poland card contains at each step and which software gate it must pass**
  - Status: done · Owner: task/m5.38-card-ladder · Critical: yes · Pair: solo
  - Result: EXP-2026-11-19-M5.38-card-ladder. Page `docs/research/card-ladder.md` (P0–P4: generated / copied / inconsistencies with the task that finds out / gate, ungated files in bold; P2 = routing, P3 = names to match the merged gate page). `tools/card_ladder.py steps --check` → `open=55 tagged=40 pending=15 missing=0`: 40 blocks tagged, 15 held in open PRs recorded in the page's Pending tags table. Measured on the factory `B48R058R` (`e9c9cb22…`): Dolnośląskie intersects 20 section-1 directories, today's writer can fill 9 (11 preserve-only `0x2146`–`0x2946`) → new **M5.53** (M5.52 was taken by M3.11c in parallel). Priorities gained "By card-ladder step".
  - Depends: — (reads `reader-coverage.md`, `roadmap.md`, M3.17's copy/generate split)
  - Goal: "a Poland card" is five different things and the board mixes them. Fix the ladder so every M4/M5 task says which step it serves, and so the first step is as small as the formats we can already write.
  - Scope: one page, `docs/research/card-ladder.md`, and a `Step:` tag on each open M4/M5/M9 task block (one line each, nothing else edited). Proposed steps — P0: EU factory card with one tile whose section 1 holds OSM roads in a `0x2046` directory, everything else factory (M5.34/M5.29/M5.30); P1: all tiles of Dolnośląskie display-only (sections 2 and 4, `LEV3456R` and `REFER001` factory, so routing and search still answer with German data — stated as a known wrong behaviour, not hidden); P2: names (section 4, `LCTBL001`); P3: routing (section 2, `LEV3456R`); P4: search (`POINT`, `ADDRE`).
  - Input: `docs/research/reader-coverage.md` (30 rows: writer, reader, L3), `docs/research/roadmap.md`, EXP-2026-11-08-M3.17 (copy set), M5.35 (`mkpoland`).
  - Hints: for each step write three lists — files generated, files copied, and *inconsistencies the firmware will see* (a P1 card has roads in section 1 that section 2 does not know). For each inconsistency name the task that finds out, in emulation, what the firmware does with it (M9.44 for file-level, M4.40/M9.13 for tile-level). The gate of a step is the set of L1/L2 checks plus the L3 targets that exist for its generated files; a file with no L3 target is listed as `ungated`, in bold.
  - Done when: the page exists; every open M4/M5/M9 block carries `Step: P0…P4` or `Step: tooling`; the Priorities section orders by step; `todo_check.py` passes.
  - Stop: do not invent format facts to fill a cell — `unknown` with the task that answers it.
  - Claims: none yet

- [ ] **M5.40 — Card ladder P0 is only checked on this host: pin the M5.34 factory-backed run as a QA manual regression**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P0
  - Depends: M5.34 (done), H84 (the `workflow_dispatch`/scheduled skeleton), M5.38 (the ladder page names P0)
  - Goal: M5.34's P0 step (`EXP-2026-11-17-M5.34-parcel`: 480 files compared, 2 differ, tile `293,990,518 B` / `b746427c…34c2ef`, `cardcheck` + targeted `l2check` rc=0) ran once by hand. Nothing on `main` fails when that run stops completing — CI has no factory tree and must not download one, so the regression today is invisible. One scheduled/manual job that reproduces the P0 gate (skip, not red, when the factory tree or OSM extract is absent) makes rule 17's "highest ladder step that passes its gate" a check, not a log line.
  - Precheck: `gh run list --workflow "CI quality gate"` shows no step that names `one_tile_pipeline --factory-root`; `grep -l 'one_tile_pipeline' .github/workflows/*.yml` prints nothing; on this host the EXP Reproduction block (its `--osm /home/marek/projekty/leafre-work/osm/dolnoslaskie-latest.osm.pbf`, or a rule-11 fetch) exits 0.
  - Scope: extend H84's workflow (or a second `workflow_dispatch`/scheduled file, name in PR) with a P0 job: resolve the factory tree and a Dolnośląskie extract from the runner cache or a rule-11 fetch, verify the factory tile SHA-256, run `python3.13 tools/one_tile_pipeline.py --factory-root … --cell B48R058R --parcel 76,940 --osm … --clip --out … --json …`, assert exit 0 and `counts.cardcheck_rc=0` with `tiles=1`, upload `report.json`; a missing input prints `SKIP (no factory tree/extract)` and is neither green-as-passed nor red. Never `pull_request`/`push`; no vendor bytes in the repo.
  - Input: EXP-2026-11-17-M5.34-parcel (Reproduction + Follow-ups), `.github/workflows/README.md`, H84's block, `tools/one_tile_pipeline.py` (`--factory-root`, `--parcel`, `--clip`, `report.json`), `tools/zlibinfo.py` (stock-zlib guard), `tools/fetch_image.py`.
  - Hints: reuse H84's exit-code policy — a missing input is exit 2/`SKIP`, not red. Assert `tiles=1` as well as exit 0 (C-3566: `tiles=0` is the footgun M5.39 closes). Record the interpreter and zlib build from `report.json`; a zlib-ng host is a skip with a reason, not a result (C-3569).
  - Done when: a `workflow_dispatch` run on a runner with both inputs completes the P0 gate and the summary names exit code, tile SHA-256/size, `cardcheck_rc`, `tiles=1` and the zlib build; with the factory tree absent it prints `SKIP (no factory tree)`; the workflow never triggers on `pull_request`/`push`; `.github/workflows/README.md` documents it; `python3 tools/selftest.py` unchanged.
  - Stop: if a runner cannot hold the 480-file factory tree and the ~90 MB extract within the job timeout, ship the skeleton with the explicit `SKIP` path and record the cache gap in the EXP; do not vendor either input.
  - Claims: C-4300–C-4309


- [x] **M5.53 — P1 needs 11 more directories: make the `0x2146`–`0x2946` section-1 kinds writable (or prove they cannot be)**
  - Status: done · Owner: task/m5.53-p1-section1-kinds · Critical: yes · Pair: required
  - Step: P1
  - Depends: M5.38 (done), M5.44 (done), M5.22 (done)
  - Goal: M5.38 measured that the Dolnośląskie bbox `14.0,49.9,17.9,51.9` intersects **20** section-1 directories of `B48R058R` and today's writer can fill **9** (5 level-1 + 4 level-2 `0x2046`); the other **11** are level-1 `0x2146` ×5, `0x2246`, `0x2346` ×2, `0x2546`, `0x2646`, `0x2946`, which `tilewriter` refuses (`PRESERVE_ONLY_DIR_KINDS`, M5.22/C-2810–C-2813). Without them P1 is a patchwork (OSM roads in 9 boxes, factory roads in 11). First slice: one `0x2146` directory.
  - Precheck: `python3 tools/parcel_census.py FAC/MAPAL001/B48R058R.DAT --sections 1 --json C.json && python3 tools/card_ladder.py dirs C.json --bbox 14.0,49.9,17.9,51.9 | tail -1` prints `section1 in bbox: total=20 spliceable=9 preserve-only=11 unmodelled=0` (prints 9/11 at base 85086f8 only; with post-M5.53 tools the factory prints spliceable=14 preserve-only=6, C-5275).
  - Scope: the record grammar inside one `0x2146` directory (non-zlib blocks, `0xffffffff` pair fields, the `n*512` tail) as far as a splice needs it; `tilewriter.py` gains mutation for that kind only with a byte-identical preserve round trip and a decode-back of the spliced records. No other kind until the first passes; no section 2/4 change.
  - Input: `tools/tilewriter.py`, `tools/parcel_census.py`, `tools/card_ladder.py dirs`, `docs/format/map-tiles.md` ("Dense tiles and roads"), EXP-2026-11-08-M5.22, EXP-2026-11-18-M5.44, `docs/research/card-ladder.md` (P1).
  - Done when: a splice of OSM ways into one `0x2146` directory (e.g. `(76,941)`) completes with `cardcheck` PASS and `l2check --semantic-tiles` PASS, the tile diff touches only that directory, and the re-run of the Precheck command on the generated tile prints `spliceable=10 preserve-only=10`; or the task is `blocked` with the exact record field that resists, an EXP with a positive control (`0x2046` splice) and a negative one. (amended 2026-11-20, pair review, C-5275: once 0x2146 is classified spliceable the class line prints spliceable=14 preserve-only=6 on factory and output alike; the token on the generated tile is the by-kind line `narrow(0x2046)=10 wide(0x2n46)=10`, factory 9/11)
  - Stop: if the non-zlib blocks cannot be decoded from bytes alone after one session, block and name the reader task (M3.25/M4.40) that would read them in the firmware; do not mutate a block whose boundary is guessed.
  - Claims: C-5270–C-5279
  - Result: EXP-2026-11-20-M5.53-wide-rows. `0x2n46` is not a tail: header word 0 is the directory size, and `0x2n46` = `0x2046` with **n wide rows** (1,024-byte body: even pair, 4+4 `u16` sub-record sizes for a 2 x 2 parcel split, odd pair; bit 31 of the row's first word marks it). New `tools/s1_wide_dir.py census` decodes 1,855/1,855 section-1 directories of 45 EU2011 tiles, 2,443,997 records all whole zlib streams, 0 overlaps; M5.22's non-zlib/`0xffffffff`/aliasing were the 512-byte misreading (C-2810–C-2812 superseded). `tilewriter` splices `0x2146` through the row model: real `B48R058R (76,941)` → `0x2046`, diff confined to the directory, `cardcheck` + `l2check --semantic-tiles` PASS, readback 16/16. Precheck token deviates on purpose: 0x2146 is now classified spliceable, so factory and output both print `spliceable=14 preserve-only=6`; the by-kind line prints `narrow(0x2046)=10 wide(0x2n46)=10` on the output (factory 9/11) — see EXP Interpretation. Follow-up **M5.54** (other kinds).

- [x] **M5.54 — P1: splice the remaining wide-row kinds `0x2246`–`0x2946`**
  - Status: done · Owner: task/m5.54-s1-wide-kinds · Critical: yes · Pair: required
  - Step: P1
  - Depends: M5.53 (done)
  - Goal: M5.53 proved every `0x2n46` directory is a `0x2046` directory with n wide rows and made `0x2146` writable (P1: 14 of 20 directories). The 6 left in the Dolnośląskie bbox (`0x2246`, `0x2346` x2, `0x2546`, `0x2646`, `0x2946`) parse with the same model (`tools/s1_wide_dir.py`) but `tilewriter` still preserves them (`PRESERVE_ONLY_DIR_KINDS`). Enable them so P1 writes 20/20.
  - Precheck: `python3 tools/s1_wide_dir.py census FAC/MAPAL001/B48R058R.DAT | tail -1` ends with `records_bad=0 block_overlaps=0 OK`, and `python3 tools/parcel_census.py FAC/MAPAL001/B48R058R.DAT --sections 1 --json C.json && python3 tools/card_ladder.py dirs C.json --bbox 14.0,49.9,17.9,51.9 | tail -1` prints `spliceable=14 preserve-only=6`.
  - Scope: `WIDE_SPLICE_DIR_KINDS` in `tools/tilewriter.py` (and its selftest), one real-tile splice per kind present in the bbox (6 directories, 6 kinds), multi-row narrowing (a directory narrows only when every wide row lost its sub-records). No section 2/4 change.
  - Input: EXP-2026-11-20-M5.53-wide-rows, `tools/s1_wide_dir.py`, `tools/tilewriter.py` (`_splice_row_model_dir`), `tools/one_tile_pipeline.py --parcel`.
  - Done when: for each of the 6 directories a pipeline run with ways over all its sub-record columns ends with `cardcheck` PASS, `l2check --semantic-tiles` PASS, `one_tile_one_directory` PASS and `s1_wide_dir census` OK on the output, and the precheck on the factory prints `spliceable=20 preserve-only=0`; a partial run (one wide row left) keeps the kind and still passes the census.
  - Stop: if a kind needs anything beyond `WIDE_SPLICE_DIR_KINDS` (a row the model cannot narrow, a record that does not re-read), block with the directory and row named.
  - Claims: C-5540–C-5549
  - Result: EXP-2026-11-20-M5.54-wide-kinds. `WIDE_SPLICE_DIR_KINDS` = `0x2146`–`0x2946`; narrowing is per directory (a partial splice keeps the kind). Seven real pipeline runs on `B48R058R`: each of the six remaining bbox directories (2–22 fixture ways from the new `s1_wide_dir.py fixture`) ends as `0x2046` with the diff confined to it, `cardcheck` + `one_tile_one_directory` PASS, `l2check --semantic-tiles --skip-mutation` PASS, census OK; the partial `(74,938)` run keeps `0x2246`. Factory precheck: `spliceable=20 preserve-only=0` (P1 20/20). Deviation: the full `l2check` FAILs only `refer_rename_resize`, identically on the untouched factory tree (C-5543) → new **M5.55**. `clarion_tile` remainder limit raised to `31*512` (C-5542); `0x2a46`+ are now preserve-only. After review: `0x2446`/`0x2746`/`0x2846` spliced by tilewriter runs on `B30R058R`/`B30R068R`/`B38R058R` (C-5548); L3 mount: the firmware reads each of the six spliced directories with `0x00414dbc` at the `0x2046` length, header-flip control DIFFERENT (C-5546/C-5547); record/sub-record decoding not covered (rule 13).


- [ ] **M5.61 — "Poland to look at": a display-only card with OSM roads in every section-1 directory of the 4 Poland tiles**
  - Status: blocked · Owner: task/m5.61-poland-card · Critical: yes · Pair: required
  - Step: P1
  - Depends: M5.53/M5.54 (all 20 directory kinds spliceable, done), M5.30 (relocation + manifest patch, done), M9.13 (container read in L3, done); M9.53 strengthens the gate (records read) but does not block the build
  - Goal: the ladder has P0 (one directory) and P1 as a census/one-tile row, but no task builds the first card a person would call a map of Poland: `profiles/poland-full.json`, tiles `B48R050R`, `B48R058R`, `B50R050R`, `B50R058R`, every level-1 and level-2 section-1 directory that intersects the profile filled from OSM; sections 2/4, `LEV3456R`, `REFER001`, `RDSTM001` and assets factory. This is the nearest result that can be shown in a car, and it measures the size budget (M7.1/M7.2) on real data.
  - Precheck: `python3 tools/mesh_grid.py cover profiles/poland-full.json <FAC>/MAPAL001` prints `contained=0 intersects=4`; `python3 tools/tilewriter.py --selftest` passes; an OSM extract is on disk (see Input).
  - Scope: build with `one_tile_pipeline.py --factory` per tile + `imgpatch` on the EU 2011 image; first on the Dolnośląskie extract (one tile, all 20 directories), then the 4 tiles. Record per tile: directories written / refused (with reason), ways in / ways dropped (class filter, parcel capacity), size delta, clusters relocated. No section 2, no names, no `LEV3456R`.
  - Input: Dolnośląskie / Poland `.osm.pbf` — **the Claude sandbox cannot download OSM (rule 12)**: a non-Claude runner or Marek puts the extract on disk (M5.1b); the committed fixture `m5.37-splice.osm` is enough for the dry run only. `docs/research/card-ladder.md` §P1, `docs/format/card-ladder.md` §P0 rows 1–10 (the gate to repeat per tile).
  - Hints: expect capacity limits before format limits — a parcel slot body is 512 B per row and a city centre may not fit; decide and record the drop rule (lowest class first) instead of failing the tile. The level-1 and level-2 directories of one area must come from the same OSM snapshot (card-ladder P0 inconsistency 1).
  - Done when: an image whose `cardcheck --image` is PASS, `imgpatch --check-diff … --allow-metadata` reports `outside: 0` for the 4 tiles + `DRSTR001.DAT`, `l2check --semantic-tiles` PASS on all 4, `7z t` OK, and `datask_l3.py mount --position` at one point per tile reads every directory with no negative status; the EXP has the per-tile table and the image SHA-256 (image outside the repo).
  - Stop: if a tile cannot hold its directories (FAT free space or a directory length the firmware does not read, M3.31), record the tile, the number and stop at the largest subset that passes.
  - Falsifier: the gate passes on a card where one directory was written with the ways of the neighbouring directory.
  - Blocker: tilewriter, not the card: (1) read_jsonl holds the whole split -> Max RSS 5.2 GB, signal 9 on B48R050R (1.6M single-cell ways) and B48R058R (M5.68); (2) the 0x2046 even/odd pair splice leaves the pair regenerated-but-unwritten, B50R058R level 1 fails (81,941,22,59): 1 changed but not regenerated (M5.69); (3) B50R050R level 2 has 1,313 parcels with no even slot (M5.70). B48R058R ingest was stopped, not attempted.
  - Unblock: M5.68, M5.69, M5.70 (the M5.71 drop-parcel check is a falsifier gap, not a build blocker)
  - Result: EXP-2026-11-21-M5.61-poland-card (negative; 1 of 4 tiles: B50R050R level 1 passes all gates, the other three hit tilewriter defects M5.68-M5.70); p1.img tile B50R050R = 7c6ea211…, template repaired
  - Claims: C-6250–C-6259

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

- [ ] **M5.64 — LCTBL: the real country/database table code for Poland, and whether the firmware actually keys LCTBL by country (the M5.60 open item)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P3
  - Depends: M5.60 (done), M5.17 (LCTBL builder, done), M4.16d (TMC reception table codes, done)
  - Goal: M5.60 built the first LCTBL ("names of places your card has") writer that the firmware's own lookup runs, but its Result leaves two things open that decide whether a Poland card's place names are found: "the real country/database numbers for Poland" and "an absent table is served from the first table (observed)" (`EXP-2026-11-20-M5.60-lctbl-index-l3`, C-6140–C-6149). M5.17's synthetic Polish set is written with a hand-picked table code; if a real unit looks up `(country 11, database 1)` and that is not the code in the file, the card's street names are not returned even though every byte round-trips. That makes this the format decision behind M5.61 ("Poland to look at") and M7.1.
  - Precheck: `python3 tools/lctbl_lookup_l3.py --selftest` prints `0 failed`; `python3 tools/lctbl_build.py synth --help` lists a table-code input; `python3 tools/tmc_reception.py table --help` resolves `(CC, LTN)` pairs (M4.16d, 14/14 on EU2011).
  - Scope: `LCTBL001.DAT` catalog in EU2011 and US2011; table code = `ord(CC hex digit) << 8 | LTN`. (1) Decode the catalog and the country/table field in both factory files: what codes exist, and whether the EU file has a table for Poland (CC 0x0?? — read, do not assume); (2) run `lctbl_lookup_l3.py` with the firmware's request `0x14e4` sub 1 for one Polish street, once with the code the catalog holds and once with the first-table fallback M5.60 observed, and show which one the firmware's answer (`0x14fb`) reflects; (3) write the rule the generator must use (M5.17/M5.61) so a generated file is looked up by the code the unit asks for. This corrects M5.60's open item, it does not redo M5.60.
  - Input: `tools/lctbl_lookup_l3.py`, `tools/lctbl_build.py` (`synth`, catalog writer), `tools/lctbl_records.py`, `tools/tmc_reception.py`, EXP-2026-11-20-M5.60-lctbl-index-l3 (C-6140–C-6149), EXP-2026-11-20-M4.16d-tmc-reception-table-codes (C-2320–C-2323), `docs/format/rdstm.md` §LCTBL, EU card `105e2032…76307`, US256 `70d945d8…04da`.
  - Done when: an EXP states the catalog codes present in the EU and US factory files (counted, per country), the Polish code a unit would request, the firmware answer for a hit vs the absent-table fallback (with the request/answer words from `lctbl_lookup_l3.py`), and a one-line rule `generator table code = ...`; `tools/lctbl_build.py` takes that rule as a flag with a `--selftest` that a wrong code makes `lctbl_lookup_l3.py` miss (negative control); `docs/format/rdstm.md` §LCTBL carries the rule and cites the run.
  - Stop: one session. If the EU catalog has no Poland entry at all and the unit's request country cannot be read from a run, write the fallback rule (a generated file must also be reachable by the absent-table path) and stop.
  - Falsifier: a generated file with the "right" table code whose Polish records are not found by the firmware, or the absent-table fallback proven not to be the first table (then M5.60's "observed" line is retracted).
  - Claims: C-6610–C-6619

- [ ] **M5.65 — Section 4 place-name index from OSM (M4.21's `generate` left names empty)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P3
  - Depends: — (tooling + layout are on `main`: M4.21 built `tools/section4.py` patch/`generate`/`verify`, M3.9 decoded the index; this task supplies the names `generate` refused to invent)
  - Goal: M4.21 makes `section4.py generate` produce verify-accepted payloads for a *changed parcel set*, but it refuses every name with no `payload_hex` — a generated Poland tile therefore has the factory's place names or none, not the OSM names inside its bbox. M5.7 solved the same problem one level down for street labels (`name_off` + odd partner names section); the section-4 admin/place index is the other half and is what place lookup and the place search read (M4.36). Fill it from OSM so a generated tile names the towns it draws.
  - Precheck: `python3 tools/section4.py --selftest` passes; `python3 tools/section4.py generate --help` shows the payload form; on a factory `B48R058R` section 4, `python3 tools/ze0-viewer/harness.py info B48R058R.DAT` shows non-zero section-4 entries with names (the positive control the generator must reproduce structurally).
  - Scope: factory EU 2011 `B48R058R` layout only (do not re-derive the section-4 grammar; M3.9/M4.21 own it). Build the OSM `place=*` / `name` side: a `places` input (IMF records M5.1c already carries `name`) → the section-4 place records of a tile, reusing `section4.py`'s `generate` payload path and its recompression (L6/w15/m8). A generated payload changed against factory must recompress only its own 64 KiB chunk (AGENTS "Writing data back"). No new grammar claim; no `ADDRE` join (that is M4.36). Excludes `REFER002`, POIs, and street labels (M5.7).
  - Input: `tools/section4.py` (`generate`, `verify`, `BuildRefused`), `tools/tilewriter.py`/`one_tile_pipeline.py` (the splice path), `docs/format/tile.md` §section 4, EXP-2026-11-08-M4.21-section4-writer, EXP-2026-11-08-M5.7-street-names-sections, M5.1c IMF `name`.
  - Done when: a Poland profile tile's section 4 carries the OSM `place` names of its bbox (a fixed list of ≥ 10 towns named in the EXP), `python3 tools/section4.py verify` accepts it on EU2011, `l2check --semantic-tiles` PASS on the tile, `harness.py info` prints at least one OSM-derived place name from the generated tile, and a negative control (a tile with no `place` input keeps the factory names byte-identically). EXP names the per-tile added/removed place count.
  - Stop: one session. If a generated place record cannot be verified against the M3.9 model after two payload shapes, record the shapes and the model mismatch and set `blocked` with the exact field that has no source — do not loosen `verify`.
  - Falsifier: a generated tile whose `section4.py verify` passes but whose viewer `info` shows a place name from the neighbouring tile's bbox (then the record indexes the wrong parcel and the writer, not the test, is wrong).
  - Claims: C-6650–C-6659

- [ ] **M5.66 — L2 visual map gate: render a generated tile to PNG and fail on a pixel diff**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: M5.61 (a generated Poland tile to render), M5.62 (section-count L2 refusal, done); reads the tile only — no writer dependency
  - Goal: every L2 check today is structural or semantic (`cardcheck`, `l2check`, `semantic-tiles`, the class golden) — none shows that the tile *looks* like a map, so a writer regression that keeps every field valid but moves the roads passes L2 and is only caught in the car (L5), which is expensive. The viewer already renders (`tools/ze0-viewer/harness.py render <tile> <out.png>`); make that a checked gate: a pinned render of a factory tile and of a generated tile, compared within a stated tolerance, so "roads in the right place" fails loudly at L2 and a human can look at a PNG before a card is cut.
  - Precheck: `python3 tools/ze0-viewer/harness.py render archive/work/B48R058R.DAT /tmp/opencode/factory.png` writes a non-empty PNG (state its byte size); `python3 tools/ze0-viewer/harness.py --selftest` passes; `python3 tools/ze0-viewer/compare_osm.py --help` is the existing geometric metric the gate can reuse for a coarse sanity number.
  - Scope: `tools/ze0-viewer/` render path plus one checked command added to the L2 ladder (a `render` subcommand or a thin `tools/render_gate.py` with `--selftest`) — no new rendering engine. Pin one factory render (small, e.g. `--levels 2 --width 800`) checked in as a vendor-free PNG **only if** it holds no decoded vendor names/bytes; otherwise pin the render hash + the geometric `compare_osm` distance and keep the PNG in `archive/`. Tolerance stated (e.g. ≤ 0.5 % differing pixels on the factory→factory control 0 %). Do not add a standing `gate.py` sub-check without the TL (rule 17 budget): this task ships the command and the L2 row, and a `Pair: required`.
  - Input: `tools/ze0-viewer/harness.py` (`render`, `compare`, `compare-tiles`), `tools/ze0-viewer/render_geojson.py`, `tools/ze0-viewer/compare_osm.py`, `docs/research/card-ladder.md` §P1 gate, the M5.61 generated tile.
  - Done when: the pinned command renders a factory tile and a generated tile and reports `PASS`/`FAIL` with a differing-pixel count; a deliberately corrupted tile (one section byte flipped) `FAIL`s; the factory→factory control is 0 differing pixels; the command has `--selftest` over synthetic tiles; the EXP holds the PNG sizes, the tolerance and the factory/generated differing-pixel counts (numbers only, no vendor bytes in the repo).
  - Stop: if a stable cross-host render is impossible (font/AA nondeterminism), pin the geometric `compare_osm` median instead of a pixel diff and record the two render hashes it could not match — do not chase renderer determinism for more than one session.
  - Falsifier: a tile whose `l2check` is PASS and whose render gate is PASS while a factory-derived `compare_osm` says the roads are hundreds of metres off (then the tolerance or the pinned view is too loose; tighten the view, not the tolerance).
  - Claims: C-6660–C-6669

- [ ] **M5.67 — The L2 result is one PASS for the whole card: no per-feature row (roads/names/POIs/geometry) says which OSM feature a generated card actually carries**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.61 (a generated Poland tile with road names/POIs to count), M5.62 (section-count refusal, done); complements M5.65 (section-4 names) and M5.66 (the visual render) — those write and render, this one counts what the firmware-facing files actually contain
  - Goal: the QA prompt asks the test system to show L2 "pass/fail per file **and per feature** (roads, names, POIs, geometry)", but `l2check.py --json` reports a `checks[]` list of file/stream digests plus `stats[name]={"features":n,"digest":…}` per `.cmp` stream — an aggregate count, not "roads written = X of Y OSM ways, names = X of Y, POIs = X of Y". A card can pass L2 with an empty road set (H103's Done-when explicitly allows it) and every number stays green. The signal the goal needs — "does the generated Poland card actually carry the roads/names/POIs the OSM input had" — is not on the ladder anywhere between L2 and a hand-run tile diff.
  - Precheck: `python3 tools/l2check.py --root CARD --json L2.json --no-cmp --no-tiles` writes a report whose keys are `checks`/`stats`/`result`; `python3 -c "import json;d=json.load(open('L2.json'));print(sorted(d))"` prints no `features`/`by_kind`/`per_feature` key; `python3 tools/l2check.py --help` lists no `--features` flag.
  - Scope: `tools/l2check.py` only — a `--features` section (on by default when `--semantic-tiles` is given) that decodes the generated `BxxRyyR.DAT` + `LEV3456R.DAT` sections and the `REFER001` POINT/ADDRE pairs into a **counted** record: `roads.class1_expected/emitted`, `roads.dir_expected/emitted`, `names.street_expected/emitted` (section-4 + LCTBL/ADDRE join), `pois.expected/emitted` (POINT records with a resolvable name), `geometry.parcels_expected/emitted`; each row `PASS` (emitted == expected), `PARTIAL` (emitted>0 and <expected, printed with both numbers) or `EMPTY` (expected>0, emitted==0 → FAIL). The expected side comes from the generator's own manifest (M5.61 writes one; if absent, `--features --expect-from MANIFEST` is required) — never from a hand-typed number. Exclusion: no new decoder (reuse `clarion_tile`/`stream_decode`/`point_census`); no golden bytes; no L3/L4 claim.
  - Input: `tools/l2check.py` (`feature_sig`/`feature_digest`, `stats`, `--semantic-tiles`), `tools/point_census.py`, `tools/addre_field_reader.py`, M5.61's generator manifest, M5.65/M5.66 (the writer/render halves), `docs/research/reader-coverage.md` rows 10–11, 17, 19 (which files carry which feature).
  - Hints: the four features map to files the matrix already names (roads → tile section 1, names → section 4 + ADDRE/LCTBL, POIs → POINT, geometry → section 1 parcels), so the `expected` side is "what the generator says it wrote", and the test is emitted-vs-expected, not a golden. An `EMPTY` road row on a card whose manifest has ways is the failure M5.61 must never ship — make it a distinct exit code so `l1l2-fixtures.yml` can block on it without blocking `PARTIAL` (a known under-fill, P2/P3 work).
  - Done when: on a generated Poland tile from M5.61 `python3 tools/l2check.py --root CARD --semantic-tiles --features --expect-from MANIFEST --json L2.json` prints one row per feature with the four counts; a card built from the same manifest with all roads stripped prints `roads.emitted=0 EMPTY` and exits 1; a `PARTIAL` card (names only) exits 0 with `PARTIAL` named; `--selftest` builds a temp manifest + tile and covers PASS/EMPTY/PARTIAL without vendor data; `python3 tools/selftest.py --only l2check` PASS.
  - Stop: if the generator does not yet write a manifest, add `--features` reading the existing `--class-emitted`/`one_tile_pipeline` record instead, and record the missing manifest as a one-line follow-up in M5.61 rather than blocking this task.
  - Falsifier: an L2 PASS on a generated card whose manifest has N road ways and whose tile decodes 0, still reported as one green `RESULT: PASS`.
  - Claims: C-6710–C-6719
  - Step: tooling

- [ ] **M5.68 — `tilewriter.read_jsonl` streams a way at a time: a 1.6 M-way split fits in RAM**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: — (`tilewriter.py` is on `main`; the negative record is EXP-2026-11-21-M5.61-poland-card §6)
  - Goal: M5.61 built `B50R050R` level 1 but could not build `B48R050R`: `tilewriter.read_jsonl` calls `_read_text(path).splitlines()`, so a 1,837,383,144 B split (1,641,585 single-cell ways) is one Python string plus a list of lines plus the parsed records. `/usr/bin/time -v` records `Maximum resident set size (kbytes): 5224528` and `Command terminated by signal 9` on a 7,735 MB host; a gzipped split peaks at `5,226,136` kB and is killed too. This is a tool limit, not a card or format limit, and it gates the other three Poland tiles.
  - Precheck: `python3 tools/tilewriter.py --selftest` passes; `python3.13 -c "import json,sys;sys.path.insert(0,'tools');import tilewriter"` then `grep -n "def read_jsonl" -A 8 tools/tilewriter.py` shows `_read_text(path).splitlines()`; `wc -l $S/B48R050R-L1.single.split.jsonl` prints `14381110` (M5.61 scratch; regenerate with `tools/m5_61_build_tile.py` if absent).
  - Scope: `tools/tilewriter.py` only — `read_jsonl` yields records from a line iterator and the callers that need the whole list are named and mapped (the M5.61 caller builds `parcel_ways`/`ways` dicts; that pass must stay O(parcels + ways) with no second full copy). Accept `.gz` by streaming the decompressor. No format change, no container change, no new CLI surface beyond what the callers already pass.
  - Input: `tools/tilewriter.py` (`read_jsonl`, `_read_text`, `splice_factory`, `verify_factory`), `tools/m5_61_build_tile.py` (the driver that hit the limit), EXP-2026-11-21-M5.61-poland-card §6 and C-6255.
  - Done when: `B48R050R` level 1 builds through `tools/m5_61_build_tile.py` from its cut PBF with a recorded `/usr/bin/time -v` peak (state the number; the same host has 7,735 MB) and the tile passes `tilewriter`'s own `verify_factory`; `--selftest` gains a streaming case (a synthetic split large enough to beat the old path's per-line cost, asserting the same records as `read_jsonl` on the small fixture); `tools/selftest.py --only tilewriter` PASS; an EXP records the peak before/after on the same input.
  - Stop: if streaming alone does not fit (the driver's own `ways` dict is the remaining copy), record both peaks and open the next task on the driver's data structure instead of masking it with a class filter.
  - Falsifier: a "streaming" reader that still returns a list of all records, or a build whose peak is unchanged on the same split.
  - Claims: C-6790–C-6799

- [ ] **M5.69 — the `0x2046` slot splice writes the even/odd pair together: `B50R058R` level 1 verifies**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: — (`tilewriter.py` is on `main`; the negative record is EXP-2026-11-21-M5.61-poland-card §6)
  - Goal: `B50R058R` level 1 reaches `tilewriter` with 429,120 single-cell ways and fails `verify_factory` with `section-1 record at (81, 941, 22, 59) changed but was not regenerated` (`tools/tilewriter.py:1182`); the same key at `c = 0` alone is clean while `c >= 1` changes the adjacent odd pair `2c+2`. A single-file tile must be able to hold its own records, so this is a writer defect that gates `B50R058R` and `B48R058R` and any city-centre tile.
  - Precheck: `python3 tools/tilewriter.py --selftest` passes; `python3.13 tools/m5_61_build_tile.py --osm $S/cut-B50R058R.osm.pbf --cell B50R058R --level 1 --factory-root $FAC --out $S/x.tile.DAT --scratch $S --report $S/x.json` prints the same `(81, 941, 22, 59)` error (M5.61 scratch; cut the PBF with the EXP's `cut4.py`).
  - Scope: `tools/tilewriter.py` only — the in-place splice region of a `0x2046` row and its even/odd partner pair (write the pair, or never rewrite a slot region whose trailing bytes belong to the partner). A fix that changes the container layout (append instead of in place) is allowed if `verify_factory` accepts it, and must keep the M5.53/M5.54 wide-row kinds passing.
  - Input: `tools/tilewriter.py` (`splice_factory` line 879, `verify_factory` line 1129, the `(81,941,22,*)` key), EXP-2026-11-21-M5.61-poland-card §6 and C-6256, `docs/format/map-tiles.md` section-1 pair layout.
  - Done when: the `B50R058R` level-1 build completes and its own `verify_factory` passes (quote the container line and the tile SHA-256), the same for one country tile as a control, `tools/tilewriter.py --selftest` keeps its current checks plus one that writes a parcel at `c >= 1` and reads the partner pair back, `python3 tools/selftest.py --only tilewriter` PASS, and `l2check --semantic-tiles` PASS on the swapped card.
  - Stop: if the pair is inherently in-place (the factory's odd records have no room), record the two record shapes and set `blocked` on a directory-aware container change instead of special-casing one key.
  - Falsifier: a fix that makes `verify_factory` skip the check, or one that passes `B50R058R` but breaks a M5.53/M5.54 wide-row kind.
  - Claims: C-6800–C-6809

- [ ] **M5.70 — level 2: the writer can create an even slot (1,313 `B50R050R` parcels have none)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: — (`tilewriter.py` is on `main`; the negative record is EXP-2026-11-21-M5.61-poland-card §6)
  - Goal: M5.61's level-2 run on `B50R050R` reports `l2_unwritable_parcels: 1313`, drops 2,624 ways for that reason (2,847 in total) and then fails with `tilewriter: check failed: no record at dir y=80 x=944 slot 5 pair 6` (`tools/tilewriter.py:1291`): the factory has no even slot for that parcel and the writer cannot create one. Without this, the second half of M5.61's Done-when (every level-1 **and level-2** directory) cannot be reached by any tile.
  - Precheck: `python3 tools/tilewriter.py --selftest` passes; `python3.13 tools/m5_61_build_tile.py --osm $S/cut-B50R050R.osm.pbf --cell B50R050R --level 2 --factory-root $FAC --out $S/x2.tile.DAT --scratch $S --report $S/x2.json` prints `l2_unwritable_parcels: 1313` and the `slot 5 pair 6` error (M5.61 scratch).
  - Scope: `tools/tilewriter.py` level-2 path only — allocate the missing even slot in the directory (the container already supports appending records, M5.30/M5.61 `appended=210`), or prove that a level-2 directory cannot grow and record it against `docs/format/tile.md`. One cell (`B50R050R`) and one factory kind first; the 20 directory kinds follow only if the first is clean.
  - Input: `tools/tilewriter.py` (`cell_mesh`, `dir_x0`, `parcel_runs` level 2, line 1291), EXP-2026-11-21-M5.61-poland-card §6 and C-6257, `docs/format/tile.md` section-1 directory/parcel rows.
  - Done when: the `B50R050R` level-2 build completes with 0 parcels left without a slot, `verify_factory` passes, the card passes `l2check --semantic-tiles` for the level-2 tiles named on `--tiles`, the L3 mount at 54.3,21.0 reads both levels with no negative status, and `--selftest` covers the created-slot case on a synthetic directory.
  - Stop: if a level-2 directory is fixed-size in the factory for every cell, record the census (empty even slots per tile) and set `blocked` with the format question named, not a writer workaround.
  - Falsifier: a build that reports 0 unwritable parcels by dropping every way that would need a slot.
  - Claims: C-6810–C-6819

- [ ] **M5.71 — `verify_factory` does not reject a legal-but-wrong parcel set (the M5.61 falsifier has no check)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: — (`tools/tilewriter.py`/`tools/l2check.py` are on `main`; the negative record is EXP-2026-11-21-M5.61-poland-card §7)
  - Goal: M5.61's falsifier is "the gate passes on a card where one directory was written with the ways of the neighbouring directory". The `--drop-parcel 80,944,5,3` control (a real parcel left factory) gives a tile of the same size (90,251,560 B) with a different SHA-256 (`6400851b…` vs `7c6ea211…`) and `tilewriter_rc: 0`, so `verify_factory` accepts it: it re-checks the splice it was handed, not "this parcel should differ from factory". No gate the task names reads the tile's parcel set against OSM, so a writer that puts a parcel's ways in the wrong slot passes every L1/L2/L3 check.
  - Precheck: `python3 tools/m5_61_build_tile.py --osm $S/cut-B50R050R.osm.pbf --cell B50R050R --level 1 --factory-root $FAC --out $S/neg.tile.DAT --scratch $S --report $S/neg.json --drop-parcel 80,944,5,3` prints `"tilewriter_rc": 0` and `"sha256": "6400851bcf78…"`; `python3.13 tools/cardcheck.py --image $S/p1.img` on the real card is PASS, so the size/container gates cannot see either difference.
  - Scope: one check in `tools/tilewriter.py --factory` (or a `--drop-guard` flag consumed by `tools/m5_61_build_tile.py`) that compares the generated section-1 record set with the factory's for the parcels the caller says it changed, and fails loudly when a parcel outside that set differs; plus `l2check --semantic-tiles` (or a new `tile_falsifier` row) that can name "parcel X holds ways not in its box". No new decoder; reuse `verify_factory`'s record walk.
  - Input: `tools/tilewriter.py` (`verify_factory` 1129, `splice_factory` 879), `tools/l2check.py` (`tile_semantic`, `tile_mutation`), `tools/m5_61_build_tile.py` (`--drop-parcel`), EXP-2026-11-21-M5.61-poland-card §7 and C-6258.
  - Done when: the `--drop-parcel` build FAILS with a message naming `80,944,5,3` and the record that changed, the real `B50R050R` build still PASSes, `--selftest` covers a synthetic parcel moved one slot (must FAIL) and the untouched factory (must PASS), and the same check is reachable from `l2check` for a swapped tile whose ways are in the neighbouring directory.
  - Stop: if the factory cannot say which parcels a caller meant to change, record the two shapes and set `blocked` on a generator manifest instead of guessing from the diff.
  - Falsifier: a check that passes the `--drop-parcel` tile, or one that fails the real `B50R050R` tile.
  - Claims: C-6820–C-6829

- [ ] **M5.72 — Road writer: point reference words the `LOC_map` walk accepts**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P1
  - Depends: M9.66 (done)
  - Goal: the generated road record of M9.53 (`tilewriter.py --factory`, `fa_encode.py`) has `0x0100` in the word the firmware treats as a point's reference to another point (record word 58, shape-buffer byte `0x48`); the walk `fn 0x0041f3dc` follows it 330 bytes past the end of the 184 B record and loads stale pool bytes (C-6776). The writer must emit this word as the firmware reads it: a word index of another point inside the record, or `0xffff`.
  - Precheck: `python3 tools/locmap_l3.py run archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --replace MAPAL001/B48R058R.DAT=G.DAT` (G built as in EXP-2026-11-21-M9.66) prints `loads beyond the 512 B window (stale pool bytes): offsets 0x202, 0x204`.
  - Scope: `tools/ze0-viewer/tools_ze0/fa_encode.py` and `tools/tilewriter.py`: (1) census of the reference word on the factory records of one tile (value, target, whether the target's own reference points back: C-6775); (2) what `fa_encode` writes at that position today and why (`0x0100`, `0x0001` look like one byte-swapped field); (3) emit in-record references for connected shapes and `0xffff` otherwise; (4) gate with `locmap_l3.py` (no load beyond the window) and the existing L2 checks.
  - Input: `tools/locmap_l3.py`, EXP-2026-11-21-M9.66-loc-map-shape-walk (C-6774–C-6777), `tools/ze0-viewer/tools_ze0/fa_encode.py`, `tools/tilewriter.py`, EXP-2026-11-20-M9.53-record-block-read.
  - Done when: a regenerated G passes `locmap_l3.py` with no load beyond the copy window, the factory census explains the word on at least 95 % of points that carry it, and the L2 checks of `tilewriter.py` still pass. EXP + claims; `docs/format/map-tiles.md`.
  - Stop: if the reference needs the result of M9.67 (the rule for counted shapes) to be testable, write the in-window part and set `blocked` on M9.67 for the rest.
  - Falsifier: factory records carry reference words that leave the record too; then the word is not a plain in-record index and the EXP must show the counter-examples.
  - Claims: C-6850–C-6859

- [ ] **M5.73 — OSM tag → POI category table for the unit's category codes**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P4
  - Depends: M4.88
  - Goal: With the category table of M4.88, define which OSM tags become which category, so the POI writer (M5.18, M5.63) has a rule set.
  - Precheck: `docs/format/poi-categories.md` exists.
  - Scope: a profile file under `profiles/` (tag expression → category code → priority), covering at least fuel, charging station, parking, restaurant, hotel, hospital, pharmacy, supermarket, bank/ATM, railway station, airport; validated by `tools/profile_validate.py`.
  - Input: `docs/format/poi-categories.md`, `tools/profile_validate.py`, `tools/osm_ingest.py`, `docs/research/osm-pipeline.md`.
  - Done when: `python3 tools/profile_validate.py profiles/…` passes; a synthetic OSM fixture with one object per rule maps to the expected code (selftest); every target code exists in the M4.88 table.
  - Stop: one session.
  - Falsifier: a rule targets a code with zero records on the factory card.
  - Claims: C-7920–C-7929

- [ ] **M5.74 — Water and forests from OSM: first slice of a background writer**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P1
  - Depends: M4.70
  - Goal: A map with roads only looks empty. After M4.70 names the background record, write lakes, rivers and forests from OSM polygons into one tile.
  - Precheck: M4.70's EXP gives the record layout and type codes; `python3 tools/tilewriter.py --selftest` passes.
  - Scope: one level-1 tile, three polygon types, simplification to the coordinate grid, ring closing and clipping at the tile frame; splice into a factory tile like the road writer; L2 round-trip (write → decode → compare geometry).
  - Input: M4.70's EXP, `tools/tilewriter.py`, `tools/osm_ingest.py`, `tools/l2check.py`.
  - Done when: `python3 tools/tilewriter.py … --background` writes a tile that `tools/parcel_census.py` decodes to the same polygons (count and vertex check), L1 and L2 pass, and `tools/datask_l3.py mount` reads it like the factory tile.
  - Stop: one session; styles/colours are whatever the type code gives.
  - Falsifier: the map client rejects or skips the record (L3 verdict differs from the factory tile).
  - Claims: C-7930–C-7939

- [x] **M5.75 — Geometry budget per level: simplification tolerance against the slot budget, measured on a synthetic town**
  - Status: done · Owner: task/m5.75-geom-budget · Critical: no · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: A parcel has a fixed slot budget (`tools/slot_budget.py`); dense OSM geometry overflows it. Measure the trade: Douglas–Peucker tolerance per level against bytes used and against visible error, and pick defaults.
  - Precheck: `python3 tools/slot_budget.py --help` and `python3 tools/tilewriter.py --selftest` work.
  - Scope: synthetic input only (a generated street grid with curves; no network): tolerances 1–20 m at level 1 and proportionally above; output bytes, vertices kept, maximum deviation; the overflow point.
  - Input: `tools/slot_budget.py`, `tools/tilewriter.py`, `tools/mesh_split.py`, `docs/research/intermediate-format.md`.
  - Done when: a table tolerance → bytes → max error per level in the EXP, produced by one command, and the chosen defaults committed in the compiler profile with a selftest that fails when a parcel overflows.
  - Stop: one session.
  - Falsifier: bytes do not fall as tolerance rises (the cost is elsewhere — record where).
  - Claims: C-7940–C-7949
  - Result: EXP-2026-11-22-M5.75-geom-budget; 20-row sweep, defaults 3m/12m at 372B, slot_budget selftest 25/25, guard PASS/FAIL 0/1

- [x] **M5.76 — A synthetic OSM town for tests without network: deterministic generator with roads, names, one-ways, POIs, water**
  - Status: done · Owner: task/m5.76-osm-synth · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: The Claude sandbox cannot fetch OSM data (rule 12), so compiler tasks stall or test on three hand-made ways. A deterministic generator gives every compiler task the same realistic input.
  - Precheck: `ls tools/fixtures` and `python3 tools/l1l2_fixtures.py --help` show what exists; reuse it if it already generates OSM-shaped input.
  - Scope: `tools/osm_synth.py --seed N --tile B50R058R -o town.jsonl` (the JSONL form `tools/tilewriter.py` reads): street grid with a ring road and a motorway, Polish names with diacritics, one-way streets, turn restrictions, 50 POIs over the categories, a river and a lake, house numbers on two streets; `--selftest` pins the SHA-256 of seed 1.
  - Input: `tools/tilewriter.py` (`read_jsonl`), `tools/osm_ingest.py`, `docs/research/intermediate-format.md`.
  - Done when: `python3 tools/osm_synth.py --selftest` passes and is in `tools/selftest.py`; `tools/one_tile_pipeline.py` (or `tools/build.py`) accepts the output and produces a tile that passes L1/L2.
  - Stop: one session.
  - Falsifier: two runs with the same seed differ.
  - Claims: C-7950–C-7959
  - Result: EXP-2026-11-22-M5.76-osm-synth-town; osm_synth selftest 24/24, deterministic seed, one-tile pipeline L1/L2

- [ ] **M5.77 — Dolnośląskie in numbers: per-tile feature counts and slot-budget overflow from the real extract**
  - Status: open · Owner: — · Critical: no · Runner: non-Claude · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: Plan the first real region with numbers: how many ways, vertices, names and POIs fall into each tile and parcel, and where the budget overflows.
  - Precheck: `curl -sI https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf` answers on the runner (not in the Claude sandbox, rule 12).
  - Scope: download (URL, date, SHA-256 recorded; the extract is never committed), `tools/osm_ingest.py` + `tools/mesh_split.py`, a per-tile and per-parcel table, the list of parcels over budget at the default tolerance.
  - Input: `tools/osm_ingest.py`, `tools/mesh_split.py`, `tools/slot_budget.py`, `docs/research/osm-vertical-slice.md`.
  - Done when: an EXP with the tile table (tile, ways, vertices, names, POIs, bytes estimated, parcels over budget) generated by one command, and the three worst parcels named.
  - Stop: one session.
  - Falsifier: no parcel overflows at level 1 (then the budget is not the constraint and the EXP says what is).
  - Claims: C-7960–C-7969

- [ ] **M5.78 — Poland in numbers: tile list, data volume and card-space estimate for the whole country**
  - Status: open · Owner: — · Critical: no · Runner: non-Claude · Pair: solo
  - Step: P1
  - Depends: —
  - Goal: The goal after Dolnośląskie is Poland. Estimate now whether it fits: tiles needed at each level, bytes per file family, total against the card size and the FAT layout.
  - Precheck: `curl -sI https://download.geofabrik.de/europe/poland-latest.osm.pbf` answers on the runner.
  - Scope: counts from the Poland extract (same recording rule as M5.77), scaled by the bytes-per-feature of the factory German tiles; compare with the space the factory card gives to a country of similar size.
  - Input: `tools/osm_ingest.py`, `tools/mesh_grid.py`, `tools/parcel_census.py`, `docs/format/sd-card-layout.md`.
  - Done when: an EXP with the estimate table and a verdict (`fits` / `fits without X` / `does not fit`), every number from a command.
  - Stop: one session.
  - Falsifier: the estimate for Germany, made the same way from OSM, is off from the factory card's real size by more than a factor of two (then the method is not usable — the control).
  - Claims: C-7970–C-7979

- [ ] **M5.79 — Charging stations from OSM into `REFER002`: feasibility and first record**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: P4
  - Depends: M4.85
  - Goal: With the station record of M4.85, write one new charging station (an OSM `amenity=charging_station`) into the EV layer and read it back.
  - Precheck: `python3 tools/refer002_census.py --selftest` passes.
  - Scope: one added record in one file, indexes updated as the container requires, in-place on a factory tree; L1/L2; the opener at L3 if located.
  - Input: `tools/refer002_census.py`, `tools/cmpind_writer.py`, `tools/mutate_refer_poi.py`, `docs/format/refer.md`.
  - Done when: `tools/refer002_census.py census` on the edited tree shows one more station at the given position; L1 and L2 pass; the EXP states which index structures had to change.
  - Stop: one session; if an index is undecoded, stop with its name (a new M4 task).
  - Falsifier: the census reads the new record but an index still points to the old record count.
  - Claims: C-7980–C-7989

- [ ] **M5.80 — Names the unit cannot draw: transliteration fallback in the compiler**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: P2
  - Depends: M4.87
  - Goal: If M4.87 finds missing glyphs, names must be transliterated (`Łódź` → `Lodz`) at compile time, in one place, with a test.
  - Precheck: M4.87's EXP has the glyph table.
  - Scope: a function in the name path of the compiler driven by the glyph table (not a fixed list), applied to road names, place names and POI names; unchanged when the glyph exists.
  - Input: M4.87's EXP, `tools/lctbl_build.py`, `tools/tilewriter.py`, `docs/research/osm-pipeline.md`.
  - Done when: selftest: each of the 18 Polish letters maps as the table says, an all-ASCII name is unchanged, and a letter present in the font is kept; one generated tile's names decode to the expected strings.
  - Stop: one session; if every glyph exists, close as 'not needed' with the M4.87 evidence.
  - Falsifier: a transliterated name collides with a different existing name in the same index and changes search order (record, do not solve).
  - Claims: C-7990–C-7999

## M6 — L5 bench/car: hardware and safety

No hardware is available now (L5). Planning tasks are open; tests wait. L4 (full-system emulator, M8) is the software integration path to prepare before L5.

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
  EXP-2026-11-06-M6.4).
  - Status: blocked · Owner: — · Critical: no
  - Depends: —
  - Goal: record the unit NAND/PROD backup procedure before any bench test, so a botched S0/S1 run is recoverable.
  - Unblock: bench access (the first S0 run, M6.2).
  - Claims: C-1930–C-1939

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

- [ ] **M6.15 — Record which firmware build Marek's unit runs**
  - Status: open · Owner: Marek · Critical: yes · **Runner: non-Claude** (hardware)
  - Depends: — (can be done in the same session as M6.2)
  - Goal: the card carries a firmware copy, the unit runs its own (`us-eu-region.md`: card `NB00` vs NAND `NB04`, HYPOTHESIS). H51 showed the EU and US card builds differ; M1.22 ports the reader addresses to the US card build. Whether the US *unit* runs that same build is unknown, and every L3 verdict for S1/S2 rests on it.
  - Input: the unit's version / service screens (the same menu family that shows the SD PIN, M2.13); photos are enough.
  - Hints: write down every version string exactly (program, navi, map, boot, audio). An agent then looks for them with `python3 tools/ce_strfind.py US256.img …` in build A/B/C of the US card image; a string found in the card's build A with the same value means "same build" for our purpose.
  - Done when: an EXP lists the strings from the screens and, per string, found / not found in US256 (offset, module), with the conclusion `same build` / `different build` / `cannot tell`.
  - Claims: C-3570–C-3579

- [x] **M6.18 — Back up the unit's flash with LeafSDTools (before any card test)**
  - Status: done · Owner: task/m6.18-unit-flash-backup · Critical: yes · **Runner: non-Claude** (hardware)
  - Depends: — (do it before M6.2 S0; C-1128: unit-side state has no backup)
  - Goal: a full copy of the unit's 8 MiB flash and its user data, so a failed card test can be undone and M6.19 can tell where the OS runs from.
  - Input: LeafSDTools card (update mode, README "GUIDE FOR QY7XXX"), menu `Read NAND`, `SRAM → DUMP TO SD`, `PRODUCT INF`.
  - Scope: read-only buttons only. Never `Write NAND`, `RESTORE SRAM`, `RESTORE VFLASH` in this task. Lock the stock card before leaving update mode (README).
  - Done when: an EXP lists file names, sizes (NAND dump expected 8 MiB minus what the tool skips; `sram_*.bin` 1,048,576 B; `vflash_*.bin` 3,014,656 B) and SHA-256; files stay outside the repo (they hold the SD PIN at `0xA100` — never commit).
  - Stop: if a size differs from the expectation, record it and stop; do not retry writes.
  - Note (2026-11-20): the start screen photo is recorded (EXP-2026-11-20-M6.18-prod-screen: `QY7200ND`, Product ID `10 20 02 12`); the files are still owed.
  - Claims: C-5200–C-5209
  - Result: EXP-2026-11-22-M6.18-unit-flash-backup (C-5203–C-5206): nand 8,388,608 B, sram 1,048,576 B, vflash 3,014,656 B, prod 722 B with SHA-256; partial files equal the ranges of the full dump; files stay outside Git

- [ ] **M6.19 — Map the unit flash dump and decide whether the OS runs from the card**
  - Status: open · Owner: — · Critical: no
  - Depends: M6.18
  - Unblock: M6.18 (the dump exists and its SHA-256 is recorded)
  - Goal: settle C-5192 (normal mode runs A/B from the card) with bytes, and name each flash region.
  - Precheck: dump size and SHA-256 match the M6.18 EXP.
  - Scope: block map of the 8 MiB (`0..0x86`, 8 KiB/64 KiB); search for `ECEC`, `NKOK`, `CLARION`, `Navi Version`, the A/B/C part numbers (`470-2824-34`, `470-2759-01`, `470-3142-00`) and compare any CE fragment with the card's bytes (`tools/cerom.py`). No PIN bytes in the EXP (mask `0xA100–0xA10F`).
  - Done when: an EXP gives a table region → content → evidence, and C-5192 becomes VERIFIED or REFUTED (negative control: the same search on a random 8 MiB of the card finds what is expected there).
  - Stop: if the dump has no recognisable structure, record the entropy map and stop.
  - Claims: C-5210–C-5219
  - Note: (2026-11-22) re-opened by M6.18 (rule 15): the dump exists, SHA-256 `dc2b30df…2cbb8b` (EXP-2026-11-22-M6.18-unit-flash-backup).

- [ ] **M2.20 — Does a region change in PROD keep the unit recoverable? (static, before anyone writes flash)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (M6.18 dump helps: real PROD checksum and blocks)
  - Goal: LeafSDTools `PRODUCT INF → RESTORE FROM SD` writes an edited PROD block (it recomputes the checksum word at `+0x2D0`), so the area byte PROD `+0x21` (`0x20` USA → `0x30` Euro, C-5201) can be changed without hardware. Before that is ever tried, answer from the code: (1) does software-update mode (build B: `UpdateMng.exe`/`PRGUpdate.exe`, the way back in) start for every area, i.e. what are the area masks of those launch-table records; (2) which launch-table records differ between USA `0x00040000` and Euro `0x00020000` on the **US** card and on the EU card (M1.34 table); (3) does the EU card's build A contain a `Navi.exe` record an area-USA unit starts.
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 IMG256 modules` lists `AppLaunch.dll`; the launch table of M1.34 (`docs/research/rom-registry.md` "The launch table") is readable for B on EU2011 and US256.
  - Scope: static, both card images (EU2011, US256), builds A and B. Output: a table record → area mask → started for USA / Euro, and the three answers. No flash write, no PROD file with the SD PIN in the repo.
  - Input: `docs/research/us-eu-region.md`, `docs/research/rom-registry.md`, EXP-2026-11-06-M2.7, M1.34, LeafSDTools `ProdInf.cpp` (`WriteProd`, facts only).
  - Done when: an EXP gives the per-area launch diff for both cards and states `update mode starts for area 0x30: yes/no/unknown` with the VA of the mask that decides it.
  - Stop: if the update-mode entry does not go through the area-filtered launch table, name the path and stop.
  - Claims: C-6260–C-6269

- [ ] **M6.21 — Region change on a unit (PROD `+0x21`): only after the card-only test, only with a way back**
  - Status: blocked · Owner: Marek · Critical: no · **Runner: non-Claude** (hardware)
  - Depends: M6.18 (flash + PROD backup with SHA-256), M6.19, M2.20 (update mode survives the change), the card-only EU test (EU card with `HDD_INFO` matched to the unit) showing that the area is what stops it
  - Unblock: all four Depends done **and** the card-only test fails for a reason M2.20 ties to the area; otherwise this task is retired as not needed
  - Goal: change the unit area by restoring an edited `prod_*.bin` with LeafSDTools, as the last resort for European maps on the US unit. Region does not gate the map checks (M2.7, C-787), so this is not expected to be needed.
  - Scope: prefer a spare unit. One byte (`+0x21`), checksum by the tool, original `prod_*.bin` kept on two media. Record every screen. Do-not-attempt on the only unit while M2.20 says `no` or `unknown` (C-1129).
  - Done when: an EXP records before/after PROD (PIN masked), what starts, audio yes/no, and the restore of the original PROD verified by a second dump.
  - Stop: any hang, black screen or missing audio → restore the original PROD at once and stop.
  - Claims: C-6270–C-6279

- [ ] **M6.22 — Rehearse S1 in the emulator: the US card with a recompressed `POINT010`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H12
  - Goal: S1 is the first changed card for Marek's US unit (a no-op recompressed `POINT010`). Before the car, boot it on `-M ze0` next to the factory US card.
  - Precheck: M8.H12 boots the US card; the S1 image builds per `docs/research/card-test-plan.md`.
  - Scope: US2011: factory US card and S1 card, same options; compare stage, launcher verdict, files read.
  - Input: `docs/research/card-test-plan.md`, `tools/imgpatch.py`, `tools/l4check.py` if merged.
  - Done when: an EXP with both verdicts and the diff of files read (expected: none); the result is linked from M6.5 through `board.py field M6.5 Input … --append`.
  - Stop: one session.
  - Falsifier: the S1 card stops earlier than the factory card.
  - Claims: C-8070–C-8079

- [ ] **M6.23 — Rehearse S2 in the emulator: find the renamed POI through the search screens**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M6.22, M8.H39
  - Goal: S2 changes one POI name. With touch input, search for it in the emulator and see the new name on screen before anyone drives to the car.
  - Precheck: M6.22 passes and M8.H39 shows a tap working.
  - Scope: US2011: scripted taps to the POI search by name, screenshot of the result list, SD trace of `POINT0nn` reads.
  - Input: `tools/ze0_ui.py`, `tools/ze0_peers/panel.py`, `docs/research/card-test-plan.md`.
  - Done when: the result list is reached on the factory card and on the S2 card, and the S2 run reads the changed page (trace) — the screenshot hashes differ between the two cards on the result screen.
  - Stop: two sessions; stop at the first screen that needs a keyboard layout not yet scripted and name it.
  - Falsifier: the result screens are identical for both cards.
  - Claims: C-8080–C-8089

## M7 — Scale and release (later)

- [ ] **M7.1** Full Dolnośląskie run, size budget.
  - Status: open · Owner: — · Critical: no
  - Depends: M5.6
  - Claims: C-1180–C-1189

- [ ] **M7.2** All-Poland road network.
  - Status: open · Owner: — · Critical: no
  - Depends: M7.1
  - Claims: C-1190–C-1199

- [ ] **M7.3** Europe motorway/trunk network.
  - Status: open · Owner: — · Critical: no
  - Depends: M7.2
  - Claims: C-1200–C-1209

- [ ] **M7.5** User guide and risk statement; "research only" until M6.7.
  - Status: open · Owner: — · Critical: no
  - Depends: M6.7
  - Claims: C-1220–C-1229

## M6 — added (PO 2026-11-09 2nd pass)

- [ ] **M6.14 — S0/S1 bench package scope artifact (Marek decision prep, no hardware)**
  - Status: open · Owner: — · Critical: no
  - Pair: solo
  - Depends: H29 (bundle/checklist concept), M5.13b (S1/S2 artifacts), M2.18 (predictor), M9.31/H45 (runnable L3 evidence/gating)
  - Goal: produce the cheap, non-hardware artifact SM retro action 5 asked for: what is in the next bench package (S0 baseline, S1), what L1/L2/L3 prechecks must be green, and what known risks (compressed sec1/data readers not runnable) are explicitly out of scope — so Marek can decide scope before hardware returns. Marek decision: S0 is 1:1 SD copy (this week); prioritize maximum L3, including loading/handling each file type, before raising S1 risk.
  - Precheck: `docs/research/card-test-plan.md` and M6.2/M6.5 describe S0/S1; M5.13b/M2.18 outputs or their EXPs are present in repo; if M9.31/H45 evidence is not yet ready, manifest records it as `BLOCKED`/`NOT_RUNNABLE` with reason (do not guess).
  - Scope: add a short doc `docs/research/bench-package-s0-s1.md` (or extend card-test-plan with a clearly marked section) plus a machine-readable manifest template (JSON/YAML, no vendor bytes) listing: card ids, required precheck commands, expected L1/L2 outputs, runnable L3 targets to run/skip with reasons, per-file-type coverage/load status, and a "known L3/L4 gaps" note (M1.2f/sec1). No image generation, no hardware steps.
  - Input: `docs/research/card-test-plan.md`, M5.13b EXP/result, M2.18 `hddinfo_predict`/acceptance, M9.31/H45/l3check/progress_report evidence format, H29.
  - Done when: the doc/template exists, references concrete task IDs and commands, and `python3 tools/claims_check.py` / `todo_check.py` still pass; a human can answer "what do we flash/check for S0 and S1?" from it without opening vendor data. Falsifier: if a required precheck command is not runnable from repo state, the manifest marks it `LOCAL_ONLY_VENDOR` or `BLOCKED` with the reason.
  - Stop: if M6.2/M6.5 scope is genuinely undecided on a safety point, record the decision as `NEEDS HUMAN` in the doc and do not guess.
  - Claims: C-3340–C-3349

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

- [x] **M8.A11 — One QEMU version: make 11.1.3 the only supported `ze0` base**
  - Status: done · Owner: Claude (task/m8.a11-qemu-single-version) · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.A9, M8.C1b
  - Goal: the `ze0` series is kept twice (`patches/` for 8.2.10, `patches/11.1/` for 11.1.3) and every patch is written, built and booted twice. Runs A and D of EXP-2026-11-21-M8.C1b give the same boot on both (C-6873). Marek, 2026-11-21: migrate fully to the new QEMU.
  - Precheck: `ls tools/qemu-ze0/patches/*.patch | wc -l` and `ls tools/qemu-ze0/patches/11.1/*.patch | wc -l` both print `13`.
  - Scope: `tools/qemu-ze0/` (`build.sh` default and pins, `run.sh`, READMEs, patch directories), the documents that name the supported version (`docs/research/qemu-ze0-port-delta.md`, `docs/format/firmware.md` register table header, `tools/README.md`). The 8.2 series is removed or frozen under a name that says so; history stays in git.
  - Input: EXP-2026-11-21-M8.A9-qemu-11-port, `tools/qemu-ze0/patches/11.1/README.md`.
  - Done when: `build.sh` with no option builds 11.1.3 from one patch directory; `build.sh --selftest`/`--dry-run` and `run.sh --selftest` pass; no document tells a reader to build 8.2; `python3 tools/gate.py` green; EXP + claims.
  - Falsifier: a boot stage or tool that works only on the 8.2.10 build.
  - Claims: C-6890–C-6899
  - Result: EXP-2026-11-21-M8.A11-qemu-single-version (C-6890–C-6893). `tools/qemu-ze0/patches/` is now one series of 13 patches for QEMU 11.1.3 (old headers kept, 11.1.3 diffs); `patches/11.1/` removed, its README is `patches/PORT-11.1.md`; `build.sh` pins only 11.1.3 and refuses 8.2. `build.sh --selftest` 78 passed; `--check-version 11.1.3` 13 applied; the patched tree equals the tree of the binary that reaches F3.
- [x] **M8.A6 — Debug serial** (`sh_serial` at `0xffe46000`; writer
  `0x8804cfa4`, pointer at `0x8804ce78`). Done when the CE boot banner
  appears or an EXP shows why not.
  - Status: done · Owner: task/m8.a6-debug-serial · Critical: no
  - Depends: M8.A2
  - Done when (made concrete 2026-11-19, the original line is kept above):
    `-M ze0` maps `sh_serial` (SCIF) at `0xffe46000` on serial port 0; a
    positive-control shim that calls the firmware writer `0x8804cfa4` makes
    `python3 tools/ze0_serial.py banner LOG` exit 0, and the same shim on
    the machine without the model exits 1; then either a real boot's
    `serial.log` passes `banner`, or the EXP names the code path the banner
    takes instead (static callers + a translated-block trace).
  - Result: EXP-2026-11-19-M8.A6-debug-serial (C-1280–C-1283). Model wired
    and proven (69-byte banner via the firmware writer; 0 bytes without the
    model). The banner never reaches the SCIF: the writer's only caller is
    the AER exception reporter, and `KernelStart` sends the banner to
    `fn 0x880404f4` → AstLog (`0x88044478`), gated `DebugLog` path off
    (`0x89e613b0`/`b4`); 60 s boots on both load extents give 0 serial
    bytes. `run.sh --serial` added (default `WORK/serial.log`). Found:
    `run.sh` sizes images from the wrong `u32` (C-1283, input for M8.A3).
    Patch: `tools/qemu-ze0/patches/ze0-0002-hw-sh4-ze0-debug-serial.patch`.
  - Claims: C-1280–C-1289

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

- [ ] **M8.C — one task per peripheral** (C1…C22, table in
  [`todo-history-2026-11-05.md`](docs/research/todo-history-2026-11-05.md),
  section M8.C). Each: read the driver init, decide stub / model / HLE,
  done when its init returns without hanging boot. Static reading of a
  driver's init can start now (Depends: —); the model waits for M8.B5.
  Claim one row at a time as `[M8.C10]` etc.; claim block: C-1360 +
  10 × row number (C1 → C-1370–C-1379, …, C22 → C-1580–C-1589). Priority
  rows: **C10 SD host**, C4 micon/power, C8 NOR flash, C18 display.
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Claims: C-1360–C-1589 (per-row blocks, see above)
  - Row notes:
    - C1 (HPB DMAC, `0xff801000` + mux/clock `0xffc08000`; F3/SD blocker): blocked 2026-11-21 (task/m8.c1-hpb-dmac). Static read: `SDHC.dll fn 0x039be010` (port 0 → ch 8) maps 0xffc08000 (ch 0–20, 0x40 stride) vs 0xff801000 (ch 21–22); ch8/ +0x0814 match C10 ACMD13 window `0x1fc08200`–`0x1fc08234`/`0x1fc08814` (C-1370–C-1372). `fn 0x039bafcc` waits >=4000 ms on `0x01f381c4` (C-1373). Helpers decoded (C-1376–C-1378): `sub_039be50c` SAR/DAR/TCR (+0x00/04/08 or +0x0C/10/14), `sub_039be4d0/59c/5d8` +0x24/28/2C, `sub_039be614` OR `(1<<ctx[0])` into common +0x0814 under 0x7530 ms sync, `sub_039be6b8` trigger +0x30/poll +0x34 bit 0; callers show two-layer completion (event wait + poll, EXP O8). DMARS ptr for ch8 computed as `0xffc0883c` (`ctx+96`) but no static runtime write/literal found; nk refs only +0x80c/810/814 (O9, C-1379). Blocker: DMARS request-source for SD ch 8 and nk ISR/INTC→event completion linkage unresolved; no `-M ze0` HPB-DMAC model/validation, so F3 remains blocked. Unblock: implement+validate HPB-DMAC in tools/qemu-ze0 and re-run C10 ACMD13 (or resolve DMARS/IRQ linkage by runtime trace). EXP: `docs/experiments/EXP-2026-11-20-M8.C1-hpb-dmac.md`. Claims C-1370–C-1379.
    - C10 (SD host): done 2026-11-20 (task/m8.c-sd-host-c10). Result: EXP-2026-11-20-M8.C10-sd-host (C-1460–C-1464). Patch `ze0-0008`: SDHI/TMIO-style ports at `0xffe4c000`/`0xffe4d000` on QEMU's SD bus (card detect = SD_INFO1 bit 5, `SDHC.dll fn 0x039bcedc`, EU2011), IRQs INTEVT `0xae0`/`0xb00` (SYSINTR `0x1f`/`0x20`, INT2 bit 29), SCIF stubs for a kernel-mode TEND spin in `serial_scif.dll`; `run.sh --sd`; tool `ze0_sdhost.py`. The launcher's SD check passes, `ActivateSDCardDriver` runs the card identification on the EU card and its init returns `End(NG)` without hanging boot; the first data transfer (ACMD13) uses the HPB DMAC and times out, so F3 (FAT mount) waits on **C1** (HPB DMAC, channel registers at `0xffc08200`).

- [x] **M8.C1b — HPB-DMAC model on `-M ze0`: SD data transfers work, the card mounts (F3)**
  - Status: done · Owner: Claude (task/m8.c1b-hpb-dmac-model) · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.B5; rows C1 and C10 of the peripheral umbrella task
  - Goal: row C1 of M8.C read the DMA engine statically and stopped with no model: `SDHC.dll` programs HPB-DMAC channel 8 (`0xffc08200`, common `0xffc08814`) for every data transfer, and on `-M ze0` the first one (ACMD13, 64 B) times out (`EventID = 2`, 4000 ms; C-1462, C-1370–C-1379). Model the DMAC in the `ze0` machine so SD reads complete and the FAT volume of the card mounts (F3). Requested by Marek 2026-11-21.
  - Precheck: `bash tools/qemu-ze0/run.sh --image archive/head256.img --machine ze0 --icount shift=0,sleep=off --sd CARD.qcow2 --timeout 240 --qemu QEMU --workdir W --log /dev/null --no-summary; python3 tools/ze0_sdhost.py serial W/serial.log` prints `activate_ng 1` and `event2_timeout 2` with the current twelve patches.
  - Scope: a new patch `ze0-0009` in both series (`tools/qemu-ze0/patches/` for 8.2.10 and `patches/11.1/` for 11.1.3): HPB-DMAC channel and common registers as `SDHC.dll` uses them, the transfer between the SD host's data port and guest RAM, the completion signal the driver waits for (event 2) and its interrupt; `tools/ze0_sdhost.py` reports the transfers. EU2011 IMG256 with the EU 2011 card behind a qcow2 overlay.
  - Input: EXP-2026-11-20-M8.C1-hpb-dmac (C-1370–C-1379), EXP-2026-11-20-M8.C10-sd-host (C-1460–C-1464), `tools/qemu-ze0/patches/ze0-0008-hw-sh4-ze0-sd-host.patch`, `tools/ze0_sdhost.py`, `tools/ze0_dbgmsg.py`.
  - Done when: one `-M ze0` boot with the card logs `ActivateSDCardDriver … End(OK` (no `EventID = 2 Timeout`), data blocks read through the DMAC equal the card image (hash of at least one block), and either the FAT volume is mounted (a file of the card is opened: F3) or the next blocker after the first block reads is named with its log line. Negative controls: the same boot with the DMAC model off reproduces the timeout; a transfer with a wrong block returns different bytes. EXP + claims.
  - Stop: if completion needs a peripheral other than the DMAC and the SD host (for example the micon), record the register or event and stop.
  - Falsifier: with a model that moves the bytes and raises every interrupt the driver enables, event 2 still times out.
  - Claims: C-6870–C-6879
  - Result: EXP-2026-11-21-M8.C1b-hpb-dmac-model (C-6870–C-6879). Patch `ze0-0009` (8.2.10 and 11.1.3): HPB-DMAC model at `0xffc08000` (status/clear/enable `+0x80c`/`+0x810`/`+0x814`; channels 8/9 = SD ports, INTEVT `0xc60`/`0xc80`, INT2 bit 19), DMA side of the SD host, card password by trust-on-first-use, three fixes of QEMU's card model (CMD6 status, CMD42 length checks), PIO gate fix, debug-SCIF area-7 alias. Boot on the EU card: `End(OK`, no `EventID = 2 Timeout`, 47 DMA transfers, 42 of 42 block reads equal to the card image (shifted control 0 of 42), LOCK+UNLOCK pass, opening image loaded, `Store Mgr Ready! [DSK1:]`, two partitions mounted: **F3 reached**. Controls: `hpbdmac=off` brings the timeout back; a card with no password is refused. Next stop: `VerInf` empty, `Error Proc<00000050>`, `FailSafe.exe` (M8.C1c). New: `tools/qemu-ze0/mkoverlay.py`, `ze0_sdhost.py dmatrace`.

- [x] **M8.C1c — Launcher after the mount: where `VerInf` comes from and what `Error Proc<00000050>` tests**
  - Status: done · Owner: Claude (task/m8.c1c-launcher-verinf) · Critical: no · Pair: solo
  - Step: reader
  - Depends: M8.C1b
  - Goal: with the card mounted under `-M ze0` (F3, C-6875) the EU2011 launcher logs `VerInf: / HddInf:QSD-302-100` with an empty `VerInf`, then `AppLch >> Error Proc<00000050>!!` and starts `FailSafe.exe` instead of `Navi.exe` (C-6877). This is the unit's own accept/reject decision for a card, in situ. Find the code, name both inputs (which file gives `HddInf`, what gives `VerInf`: flash, registry, micon?) and the comparison, and say what the emulator must provide for the applications to start.
  - Precheck: `python3 tools/ze0_sdhost.py serial SERIAL.log` of a `-M ze0` boot with `ze0-0009` and the EU card prints `store_ready 1`, `applch_error 1`, `failsafe_start 1`.
  - Scope: EU2011 launcher (`AppLch`): the function that prints `VerInf: %s / HddInf:%s`, its callers and the `Error Proc<%08x>` path for code `0x50`; static first, then one `-M ze0` run that confirms the branch (`tools/ze0_dbgmsg.py run --hook`).
  - Input: EXP-2026-11-21-M8.C1b-hpb-dmac-model, `tools/sh4xref.py`, `tools/cerom.py`, `tools/ze0_dbgmsg.py`, M8.E2 (registry as loaded), `docs/research/us-eu-region.md`.
  - Done when: the two inputs and the test are named with VAs and one run shows the branch taken; either a machine option or stub makes the launcher pass the check and the next log lines are recorded, or the missing input (for example a flash block) is named. EXP + claims.
  - Stop: if `VerInf` comes from the micon or the NOR flash user area with no static default, record the access and stop (rows C4/C8 of M8.C).
  - Falsifier: the launcher reaches `Error Proc<00000050>` on a path that does not read `VerInf` or `HddInf`.
  - Claims: C-6880–C-6889
  - Result: EXP-2026-11-22-M8.C1c-launcher-verinf (C-6880–C-6886). `VerInf` is not a NAND record: `KernelIoControl(0x0101302C)` (nk.exe B `fn 0x88049e28`) returns start and length of XIP region `index`; the launcher asks for index 0 = ROM image B, so `VerInf` = header `+0x60` (11 chars) and the map-DB window = `+0x70`/`+0x72` (BE u16), phys `0x08000060`. The card has zeros there, so a unit writes them after loading image B (IPL, hypothesis). Patch `ze0-0010`: `-M ze0,verinf=QSD-302-100,mapdb=16-16` (`run.sh --verinf/--mapdb`) passes both checks, no `Error Proc`, no FailSafe; controls give `0x50` and `0x51`. Next stop: `CInaiProtocol` `WriteFile` (6:0) loop = serial DMA, row C2.

- [x] **M8.C2a — Serial DMA on `-M ze0`: HPB-DMAC channels 1/3/7 (receive) and 10 (transmit) for SCIF1/3/7**
  - Status: done · Owner: Claude (task/m8.c2a-serial-dma) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1c
  - Goal: with the launcher checks passed (M8.C1c, C-6883) the first application failure is the audio-network protocol: `CInaiProtocol` `WriteFile` returns 0 of 6 bytes (`Write size disagreement. (6:0)`) in a loop (C-6886). `serial_scif.dll` sends through HPB-DMAC channel 10 (RAM `0xa999a000` → SCIF1 FTDR `0xffe4100c`) and receives through channels 1/3/7 (SCIF1/3/7 FRDR → two 0x80-byte RAM buffers each); the `ze0-0009` model only stores those registers. Model the transmit path end to end (bytes reach the SCIF, the channel completes, its interrupt fires) and the receive channels as armed-without-data, and record what the protocol does next.
  - Precheck: `-M ze0,verinf=QSD-302-100,mapdb=16-16,hpbdmac-trace=on` boot of EU2011 IMG256 with the EU card: the trace has writes to channel 10 (`+0x280` = `0xa999a000`, `+0x284` = `0xffe4100c`) and channels 1/3/7 (`+0x040`/`+0x0c0`/`+0x1c0` = SCIF FRDR); the serial log has `Write size disagreement. (6:0)`.
  - Scope: `ze0_hpbdmac.c` (channels other than 8/9: memory → SCIF FTDR, interrupt lines INTEVT `0xb60 + 0x20 × ch`, INT2 bit 19), `ze0_intc.c` sources, `ze0.c` wiring; nk.exe ISRs for the serial channels (`0xb80`/`0xbc0`/`0xc40`/`0xca0`); `tools/ze0_sdhost.py` markers. No peer device (micon, audio unit) is modelled.
  - Input: EXP-2026-11-21-M8.C1b-hpb-dmac-model, EXP-2026-11-22-M8.C1c-launcher-verinf, `tools/ze0_sdhost.py inttable`, `tools/sh4dis.py`.
  - Done when: a boot shows channel-10 transfers with the bytes logged (`hpbdmac-trace`), `Write size disagreement` gone or explained, the next stop recorded; control `hpbdmac-serial=off` (or equivalent) brings the `(6:0)` loop back. EXP + claims.
  - Stop: if a transmit completes only with a reply from the peer (micon/audio unit), record the protocol bytes and stop (row C4, F4 decision M8.D2).
  - Falsifier: `WriteFile` still returns 0 with channel 10 completing and its interrupt delivered.
  - Claims: C-6900–C-6909
  - Result: EXP-2026-11-22-M8.C2a-serial-dma (C-6900–C-6905). `serial_scif.dll` sends through HPB-DMAC channel 10 (RAM `0xa999a000` → SCIF1 FTDR) and receives through 1/3/7 (SCIF1/3/7 FRDR → two RAM planes); their ISRs (INTEVT `0xb80`/`0xbc0`/`0xc40`/`0xca0`) return SYSINTR `0x13`. Patch `ze0-0011` (`hpbdmac-serial`, default on): channel 10 moves each frame to SCIF1 and completes, the driver takes each interrupt (9 675 frames `10 02 02 08 00 10 03 19` in 330 s). The protocol still fails at `GetWriteResult … failed wait response`, with and without the transmit (control `hpbdmac-serial=off`): it waits for the audio unit at the other end — stop condition, F4 (M8.D2). Next: receive path + SCIF1 chardev so a host script can answer.

- [x] **M8.C1d — Multi-XIP on `-M ze0`: join ROM A (the applications) to the running kernel, then dump the screen**
  - Status: done · Owner: Claude (task/m8.c1d-multi-xip) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C2a
  - Goal: Marek (2026-11-22, "Tak, go"): with M8.C1c/M8.C2a every application `CreateProcessW` (Navi.exe, AuiApp, SystemExe, DrawOi, …) fails; make the kernel see ROM A (image at file `0x200200`, 149 modules, no `nk.exe`) the way the unit's IPL would, so the applications start; add a host script that turns the VRAM into a PNG (Marek: "odpalić maszynę i po jakimś czasie zrobić screenshot").
  - Precheck: run L (`-M ze0,verinf=QSD-302-100,mapdb=16-16`, 1000 s) logs `Rom chain NOT found`, `AppLch >> Single NK Image` and `Launch Process Not Create!!! -> \windows\Navi.exe`.
  - Scope: kernel `.data` fixups read by OEMInit (XIP-chain pointer, boot type, NK2 base), ROMHDR fields, TOC layout of images A/B; a host tool that writes the IPL patch; a `ze0` option that applies it; a VRAM → PNG tool. No guest byte on the card changes.
  - Input: EXP-2026-11-22-M8.C1c-launcher-verinf, EXP-2026-11-22-M8.C2a-serial-dma, `tools/cerom.py`, `tools/sh4dis.py`, gdb remote stub of QEMU.
  - Done when: a boot with the patch logs `Rom chain found`, has no `Launch Process Not Create`, and shows code of a ROM-A-only DLL running (a log line from it); the screenshot tool writes a PNG from a running guest; the next blocker recorded.
  - Stop: if the kernel cannot run with both images at once (overlapping module addresses), record which modules collide and what a real unit must hold instead (NK1 in flash), and stop at the smallest working subset.
  - Falsifier: with the chain in place, `CreateProcessW` for `\windows\Navi.exe` still fails with LastError 2.
  - Claims: C-6910–C-6919
  - Result: EXP-2026-11-22-M8.C1d-multi-xip (C-6910–C-6917). The audio unit is not the blocker (27 ACM 30 s timeouts, then `Finish Launch Threads!`); every application `CreateProcessW` failed with LastError 2 because ROM image A (Navi.exe etc.) was never joined: nk.exe reads an XIP-chain pointer from a `.data` fixup (var `0x89e43c90`) that the card leaves at -1. `tools/ze0_ipl.py` + `ze0-0012` (`ipl-patch=FILE`) write the chain, RAM end `0x8c6e0000` and compacted TOCs (A and B overlap in the DLL space, C-6913): `Rom chain found`, 0 `Not Create` (was 19), Navi.exe's OSMDLL/OBJDLL run. `tools/ze0_screenshot.py` saves the VRAM as PNG; it stays black because the display engine (phys `0x1ff80000`/`0x1fe80000`) is not modelled → M8.C1e.

- [x] **M8.C1e — Display engine on `-M ze0`: trace, then a minimal DU/2D model so the VRAM fills**
  - Status: done · Owner: Claude (task/m8.c1e-display-engine) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1d
  - Goal: Marek wants to boot the emulator and take a screenshot after a while (2026-11-22). With M8.C1d the applications run but the VRAM (phys `0x0e700000`) stays zero; `gdisubdrv.dll` drives two register blocks that `-M ze0` does not model (C-6916).
  - Precheck: run P of EXP-2026-11-22-M8.C1d-multi-xip with `-d invalid_mem` shows `Invalid read/write at addr 0x1FF80…` and `0x1FE80…`; `tools/ze0_screenshot.py grab` prints `no non-zero pixel`.
  - Scope: a trace device at phys `0x1ff80000` and `0x1fe80000` (log every access with PC); `gdisubdrv.dll` code around `IntrThread_DU`/`IntrThread_2DG` and the `VirtualCopy` sites (`0x3af31b6`, `0x3af3224`); then the smallest model (register file, vsync/DU interrupt, 2D command completion) that lets drawing reach the VRAM. Alternative to evaluate: registry `System\Automotive\Graphic\Engine` = 0 (software renderer).
  - Input: EXP-2026-11-22-M8.C1d-multi-xip, `tools/ze0_ipl.py`, `tools/ze0_screenshot.py`, `tools/sh4dis.py`.
  - Done when: `tools/ze0_screenshot.py grab` writes a PNG with non-zero pixels from a running guest, or the access trace and the reason no pixel arrives are recorded.
  - Stop: if the 2D engine needs a command-list interpreter larger than a register model, record the command format and stop (F5 boundary, M8.C19).
  - Falsifier: with both blocks answering, the VRAM stays zero for the whole run.
  - Claims: C-6920–C-6929
  - Result: EXP-2026-11-22-M8.C1e-display-engine (C-6920–C-6927). `ze0-0013` adds device `ze0-gfx` (DU phys `0xfff80000`, 2DG `0xffe80000`, `gfx-trace=on`): 60 Hz vblank (INTEVT `0x3e0`, SYSINTR 33) and the 2DG start/end handshake (DLSAR + SCLR = 1 → SR.TRA, INTEVT `0x780`, SYSINTR 34). Two more blockers fixed: `serial_scif.dll` spun on SCIF channel 8 and starved the UI (stubs now 0–9), and Navi.exe died on `fldi1` with `FPSCR.PR = 1` in XGLDLL (board flag `sh4_fldi_any_pr`). The UI now runs to idle, starts 2DG display lists and writes bitmaps/glyphs into VRAM, but no screen frame exists until the lists are executed (Stop case); list format in O9 → M8.C1f. `Engine = 0` is no shortcut.

- [x] **M8.C1f — 2DG display-list interpreter on `-M ze0`, so `ze0_screenshot.py` shows the UI**
  - Status: done · Owner: Claude (task/m8.c1f-2dg-interpreter) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1e
  - Goal: Marek wants to boot the emulator and take a screenshot after a while (2026-11-22). After M8.C1e the UI submits 2DG display lists (DLSAR + SCLR) and uploads glyphs/bitmaps into VRAM, but nothing executes the lists, so no screen frame exists (C-6925).
  - Precheck: run G7 of EXP-2026-11-22-M8.C1e-display-engine (`ze0-0013`, `ipl-patch`, `gfx-trace=on`) shows `2dg wr +0x0000/4 = 0x00000001` lines and VRAM blocks with non-zero bytes but no 800 × 480 frame.
  - Scope: execute lists in `ze0-gfx` at SCLR = 1: register writes (`0x18000000`, `0x28000080` block), sync `0x08000000`, end `0x12000195`, filled quads `0xa0003000` first, then glyph/bitmap blits `0xa8003100` and the matrix commands (`0xe0003020`, `0xd0007038`, `0x80003220`); find the render-target registers; then compose DU planes 2/3/4 (`+0x200/0x300/0x400`, address at `+0x20`, stride at `+0x04`) in `tools/ze0_screenshot.py`. Spec source: the list builder in the AUI renderer (`auirtdll.dll`), the dumped lists (C-6926).
  - Input: EXP-2026-11-22-M8.C1e-display-engine (O8, O9), `ze0-0013`, `tools/ze0_screenshot.py`, `tools/sh4dis.py`.
  - Done when: `tools/ze0_screenshot.py grab` writes an 800 × 480 PNG of a DU plane that shows filled rectangles or text drawn by the 2DG model from a running guest, with a list-level log of which commands were executed and which were skipped.
  - Stop: if the matrix commands turn out to be a general textured-polygon rasteriser, implement fills and axis-aligned blits only, record the rest, and stop.
  - Falsifier: with fills executed, the DU plane memory stays zero after the lists that fill it.
  - Claims: C-6930–C-6939
  - Result: EXP-2026-11-22-M8.C1f-2dg-interpreter (C-6930–C-6936). `ze0-0014` adds `hw/sh4/ze0_2dg.c`: each 2DG display list runs on the host when SCLR = 1 is written (boxes, alpha glyphs, stencil-then-cover polygons, polylines, textured quads; pixels are (A)RGB1555, not 565). `tools/ze0_screenshot.py screen` composes the DU planes (plane 4 = map on a 2368-wide surface, plane 2 = keyed UI). Within 15 minutes the EU 2011 card shows the London map; 2669 commands drawn, 7 skipped (`0xb3007602`, `0xb10038c2`). The UI layer is still empty.

- [x] **M8.C1g — UI layer on `-M ze0`: AuiApp from image A, COM registrations, screenshot with the AUI forms**
  - Status: done · Owner: Claude (task/m8.c1g-ui-layer) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1f
  - Goal: Marek wants the UI layer (buttons, status bar) in the emulator screenshot (2026-11-22). After M8.C1f only the map plane is drawn; the UI plane stays keyed out.
  - Precheck: with `ze0-0014` and the M8.C1d IPL patch, `serial` shows `CAuiMonitorCmn::ThreadProc::TIMEOUT!!!!!` and `Pow >> Pow Off 1st Detect!!!` (SystemEXE shuts the system down 45 s after start because no AUI form loaded); DU plane 2 holds only `0x83ff`.
  - Scope: (1) why AuiApp never loads a form: the kernel image's updater `auiapp.exe`/`auirtdll.dll` win over image A's in `ze0_ipl.py`; (2) `ze0_ipl.py --prefer-app` to keep image A's copies; (3) the skin path the unit's registry would give (`SkinPath`); (4) COM registrations of image A's `*CC.dll` controls, which live in the unit's own registry, not on the card (from each DLL's `REGISTRY` resource); (5) plane alpha (`+0x08`) in `ze0_screenshot.py`; (6) screenshot.
  - Input: EXP-2026-11-22-M8.C1f-2dg-interpreter, `tools/ze0_ipl.py`, `tools/cehive.py`, `tools/cerom.py`, `docs/format/skins.md`.
  - Done when: a screenshot from a running guest shows at least one AUI form element drawn by AuiApp (not by Navi.exe), or the EXP names the missing piece with the serial-log evidence.
  - Stop: if the forms need processes that fail for a missing unit-flash DLL (`HCXMemory.dll`, `AppTimerDll.dll`), record which and stop.
  - Falsifier: with image A's AuiApp, the skin path and the COM registrations in place, `AUI:WRN:02034302 Failed initialize control` still appears for every control.
  - Claims: C-8200–C-8209
  - Result: EXP-2026-11-22-M8.C1g-ui-layer (C-8200–C-8207), stopped on the Stop case. `ze0_ipl.py --prefer-app auiapp.exe,auirtdll.dll` runs image A's AuiApp instead of the updater's; `tools/ze0_aui.py` patches in the SkinPath default, `DllRegisterServer` of 64 control DLLs and (`--no-aui-timeout`) SystemEXE's 45 s AUI wait. The real skin chain loads (ReleaseMain.skn → Substance.skn, 36 905 skins) and the system no longer shuts down, but 16 controls incl. `ctl_PRCOM_System` fail: `HCXLog.dll`, `HCXMemory.dll`, `Cws_Apl.dll` are in the unit's flash, not on the card. `ze0-0015` adds 2DG op 0x44. Next: M8.C1h stubs.

- [x] **M8.C1h — UI layer on `-M ze0`: stub `HCXLog.dll`/`HCXMemory.dll`, image C's `AppTimerDll.dll`, first AUI form on screen**
  - Status: done · Owner: task/m8.c1h-hcx-stubs · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1g
  - Goal: Marek wants the UI layer in the emulator screenshot (2026-11-22). M8.C1g got image A's AuiApp running with the real skins, but 16 controls (incl. `ctl_PRCOM_System`) fail because their DLLs import libraries that live in the unit's flash, not on the card.
  - Precheck: with `ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll` + `ze0_aui.py --no-aui-timeout`, the serial log shows `DoImport Failed! Unable to import Library 'HCXLog.dll'` (17×), `'HCXMemory.dll'` (12×), `'Cws_Apl.dll'` (15×), `'AppTimerDll.dll'` (4×) and 16× `AUI:WRN:02034302 Failed initialize control`.
  - Scope: (1) semantics of `HCXLog.dll` ordinals 1, 2, 4–7 and `HCXMemory.dll` ordinals 1, 3–6, 9–19, 23, 24, 29 from their call sites in the 45/58 importers (`tools/sh4xref.py --to SLOT`, `tools/callgraph.py`); (2) a stub ROM module per DLL (exports by ordinal, minimal SH-4 bodies: logger = no-op returning success, allocator = forward to coredll `LocalAlloc`/`LocalFree` or equivalent) added to the IPL TOC; (3) image C's `AppTimerDll.dll` in the merged TOC; (4) `Cws_Apl.dll` only if a non-telematics control needs it; (5) screenshot.
  - Input: EXP-2026-11-22-M8.C1g-ui-layer, `tools/ze0_ipl.py`, `tools/ze0_aui.py`, `tools/cerom.py`.
  - Done when: a screenshot from a running guest shows at least one AUI form element drawn by AuiApp, or the EXP names the next missing piece with serial-log evidence.
  - Stop: if an HCX ordinal returns a structure whose layout cannot be read from the callers, record which and stop.
  - Falsifier: with the stubs loaded, `ctl_PRCOM_System` still returns `80020003`.
  - Claims: C-8210–C-8219
  - Result: EXP-2026-11-22-M8.C1h-hcx-stubs (C-8210–C-8216). `ze0_stubdll.py` + `ze0_ipl.py patch --stub-dlls hcx` add stub ROM modules for `HCXLog.dll`/`HCXMemory.dll` (C++ base classes; every ordinal returns `this`, HCXMemory #23 = named file mapping), placed in gwes.exe's dropped pages. All HCX imports resolve, failed controls 16 → 5 (only Cws_Apl/AppTimerDll), `ctl_PRCOM_System` initialises. AuiApp still paints no form (only clears), also with `ze0_aui.py --start-form frm_PRAGR_AgreeCaution`; likely gated by the power/display sequence with the audio microcontroller (hypothesis). Next: M8.C1i, M8.H43–H45.

- [x] **M8.C1i — UI layer on `-M ze0`: what makes AuiApp paint its first form**
  - Status: done · Owner: task/m8.c1i-aui-paint · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1h
  - Goal: Marek wants the UI layer in the emulator screenshot (2026-11-22). After M8.C1h every non-telematics control loads, but AuiApp only clears its surface, even with StartForm = `frm_PRAGR_AgreeCaution`.
  - Precheck: with `ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll --stub-dlls hcx` + `ze0_aui.py --no-aui-timeout`, `qemu -d unimp` with `gfx-trace=on` shows only two lists targeting the AUI surface, both clears.
  - Scope: (1) the path from form load to `CFormRender` drawing in `auirtdll.dll`/`auiapp.exe` and the condition that stops it (display state, `SYS_REQ_ACTIVATE` to `MSG_PROCESS_OFF`, ScreenStateCC); (2) whether the gate is the microcontroller start handshake (M8.H43–M8.H45) or a value the IPL patch can set; (3) `AppTimerDll.dll` from image C via `ze0_stubdll.py`-style placement; (4) screenshot.
  - Input: EXP-2026-11-22-M8.C1h-hcx-stubs, `tools/ze0_stubdll.py`, `tools/ze0_aui.py`, `docs/format/skins.md`.
  - Done when: a screenshot from a running guest shows at least one AUI form element drawn by AuiApp, or the EXP names the gate with the code path that checks it.
  - Stop: if the gate is the microcontroller handshake, record the call chain and hand over to M8.H44.
  - Falsifier: forcing the suspected gate open still leaves the AUI surface cleared only.
  - Claims: C-8230–C-8239
  - Result: EXP-2026-11-22-M8.C1i-aui-paint-gate (C-8230–C-8239). No form after `frm_PRCOM_StartUp` loads: auirtdll's draw routine (fn `0x037c5440`) polls about twice a second with nothing pending, no control is created, and AuiMonitoringCC (which sets INIT_END from its init) never exists, hence SystemEXE's 45 s watchdog. New `ze0_ipl.py patch --copy-dlls apptimer` copies `AppTimerDll.dll` from image C (moved; RW page must be in the kernel's DLL data window). Audio.exe (the `MSG_PROCESS_OFF` source SystemCC asks to activate) now starts, then waits for ACM module 6 behind the silent audio microcontroller. Gate chain handed over to M8.H43/M8.H44; M8.C1j tests the activation hypothesis without the microcontroller.

- [x] **M8.C1j — UI layer on `-M ze0`: answer the audio-source activation without the microcontroller**
  - Status: done · Owner: Claude (thread Zamontuj kartę SD w QEMU) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1i
  - Goal: Marek wants the UI layer in the emulator screenshot (2026-11-22). M8.C1i found that no form after `frm_PRCOM_StartUp` loads; the likeliest gate is SystemCC's `SYS_REQ_ACTIVATE` to `MSG_PROCESS_OFF` (Audio.exe), which Audio.exe never answers while the audio microcontroller is silent (C-8237, C-8238 HYPOTHESIS).
  - Precheck: with `ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll --stub-dlls hcx --copy-dlls apptimer` + `ze0_aui.py --no-aui-timeout`, the serial log has `[Audio::] Create Thread[1] Wait Modules Error LaunchId=[45] Wait Modules ID=[6]` and no `SYS_NOTIFY_ACTIVATE_COMPLETE`.
  - Scope: (1) how SystemCC receives `SYS_NOTIFY_ACTIVATE_COMPLETE` (`0x81120012`) and which window message (`0x1983`, `0x1a44`–`0x1a58`) it then raises toward `NotifySysEvent`; (2) deliver that answer in the guest (IPC message injected by an IPL routine, or a patched branch in Audio.exe's OFF source), recorded as an emulator-only patch; (3) breakpoints on control creation (fn `0x037dffdc`) and invalidation (fn `0x037def48`) with a step-over client (C-8239); (4) screenshot.
     (5) M8.C1k O4: with the real HCXMemory (`--copy-dlls unitflash`), ScreenState reports CC window id 16 unregistered and message 6525 (`0x197d`) to it failing; find which CC owns id 16.
  - Input: EXP-2026-11-22-M8.C1i-aui-paint-gate, `tools/ze0_aui.py`, `tools/ze0_stubdll.py`.
  - Done when: a screenshot shows an AUI form element, or the EXP shows that the injected answer reaches SystemCC and the skin still loads no form (then C-8238 is refuted and the next wait is named).
  - Stop: one session; if the answer needs Audio.exe's full source state machine, hand over to M8.H45.
  - Falsifier: with the answer injected and logged by SystemCC, `0x037dffdc` and `0x037def48` stay silent.
  - Claims: C-8280–C-8289
  - Result: EXP-2026-11-22-M8.C1j-audio-activate (C-8280–C-8286; C-8238 retracted, C-8233 narrowed). Audio.exe's launcher (fn `0x000268b8`) skips its threads when WaitModule(6) fails, so `SYS_REQ_ACTIVATE` was never handled. New `ze0_aui.py --skip-module-wait audio.exe`: the exchange completes and SystemCC fires `NotifySourceChange`, but no form follows and the screen stays the map. With `--copy-dlls unitflash` auirtdll creates 18 controls early in both variants. Next: M8.C1l (what `frm_PRCOM_StartUp` waits for in the skin).

- [x] **M8.C1k — UI layer on `-M ze0`: real unit-flash DLLs from NK1 instead of stubs**
  - Status: done · Owner: Claude (thread "Zamontuj kartę SD w QEMU") · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1i
  - Goal: Marek sent a LeafSDTools dump of his unit's flash (2026-11-22) and asked to put the system files into the repository so QEMU is easier to start. The NAND holds NK1, the CE image image A was built against, with the real `HCXLog.dll`, `HCXMemory.dll` and `AppTimerDll.dll` that M8.C1h stubbed and M8.C1i copied from image C.
  - Precheck: `tools/nk1_extract.py NAND --list` shows a 51-module CE image at 0x40000.
  - Scope: (1) cut NK1 out of the dump (`tools/nk1_extract.py`), check it for the unit serial, unit key, lock password and VIN-shaped strings, commit it as `firmware/unit-flash/nk1-QY7200ND.bin` (owner's decision, AGENTS.md exception); (2) `ze0_ipl.py patch --copy-dlls unitflash [--nk1 PATH]` copies the three modules into image A, compressed sections stored decompressed; (3) one run against the M8.C1i baseline (H10).
  - Input: EXP-2026-11-22-M8.C1i-aui-paint-gate, `tools/ze0_stubdll.py`, `tools/nk_decomp.py`.
  - Done when: the run loads the real modules (their own log lines appear) and the EXP records what changes against H10.
  - Stop: one session.
  - Falsifier: with the real modules, controls fail that loaded with the stubs.
  - Claims: C-8290–C-8299
  - Result: EXP-2026-11-22-M8.C1k-unit-flash-nk1 (C-8290–C-8297). NK1, the unit-flash CE image (51 modules), is cut from Marek's NAND dump by `tools/nk1_extract.py` and committed as `firmware/unit-flash/nk1-QY7200ND.bin` (owner's decision; checked for serial, unit key, password, VIN). `ze0_ipl.py patch --copy-dlls unitflash` copies the real HCXLog/HCXMemory/AppTimerDll (moved; HCXMemory's compressed sections decoded by image B's kernel routine). The real HCXMemory runs (CreateSharedBuffer lines), failures are unchanged (16 imports: Cws_Apl, BOLERODLL; 6 controls), ScreenState now reports CC window 16 unregistered; the paint gate (Audio.exe/ACM module 6) is unchanged. Next: M8.C1j.

- [x] **M8.C1l — UI layer on `-M ze0`: what `frm_PRCOM_StartUp` waits for before the next form**
  - Status: done · Owner: Claude (thread Zamontuj kartę SD w QEMU) · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1j
  - Goal: Marek wants the UI layer in the emulator screenshot (2026-11-22). M8.C1j showed that the audio-source activation completes with `ze0_aui.py --skip-module-wait audio.exe` and SystemCC fires `NotifySourceChange`, yet no form follows `frm_PRCOM_StartUp` (C-8284); the start form's controls are created (C-8285).
  - Precheck: run J3's configuration (`ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll --copy-dlls unitflash` + `ze0_aui.py --no-aui-timeout --skip-module-wait audio.exe`) shows `SYS_NOTIFY_ACTIVATE_COMPLETE` in the serial log and only the map on screen.
  - Scope: (1) decode `ReleaseMain.skn`'s records for `frm_PRCOM_StartUp`, `act_PRCOM_SystemInit`, `var_PRCOM_SystemInitFlg`, `act_SYSCOM_NotifySysEvent` and the Show/Start records (`tools/skn_info.py`); (2) name the event or variable that moves to the next form and who raises it (SystemCC method, SystemEXE IPC, vehicle input); (3) list the 6 failing controls by CLSID and check whether one of them is on that path; (4) raise it in the guest as an emulator-only patch and take a screenshot.
  - Input: EXP-2026-11-22-M8.C1j-audio-activate, EXP-2026-11-22-M8.C1i-aui-paint-gate, `tools/ze0_aui.py`, `tools/skn_info.py`.
  - Done when: a screenshot shows an AUI form element, or the EXP names the input the start form waits for, with the skin record and the firmware code that would raise it.
  - Stop: one session; if the input is a vehicle signal over the micom/CAN, hand over to M8.H43–M8.H45 with the frame it needs.
  - Falsifier: the start form's records contain no transition (no Show/Start of another form), i.e. the next form comes from outside the skin.
  - Claims: C-8320–C-8329
  - Result: EXP-2026-11-22-M8.C1l-object-store-registry (C-8320–C-8327). Control registration stopped after ~52 DLLs because kernel B fixes the object store (RAM registry hive) at 80 pages in OEMCalcFSPages. New `ze0_aui.py --object-store` (hook returns the TOC value, ulFSRamPercent 0x00808028, 592 pages): every DLL registers. ScreenStateCC = CC window 16 now runs (also `--register-first`), CC window ids mapped from code; the screen state stays in `INI_STARTUP`, windows 40/41/46 (UnitMainte, EvNotice, InfoBar) are missing, 29 controls fail init, screen still the map. Next: M8.C1n; M8.C1m (unit data) added.

- [ ] **M8.C1m — `-M ze0` with the unit's own NAND/VFlash/SRAM: does the EU card boot against US unit data?**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1k
  - Goal: Marek (2026-11-22, relayed by the coordinator) wants the EU card run in `-M ze0` with the data of his US unit (NAND, VFlash, SRAM dumps from M6.18) instead of the hand-set `verinf=`/`mapdb=` values and stand-ins. His hypothesis: the region (Product ID `10 20 02 12`, area USA) lives in the unit's NAND/flash and the EU card will not start. This also tests the launcher's gates (`DIFFERENT MAP CODE`, `MAP DATA BASE UNMATCH`) on real data.
  - Precheck: the three dumps are outside the repository in the worker's directory (never committed, nor their hashes for PROD); `ze0_ipl.py patch --copy-dlls unitflash` boots to `AppLch >> Finish Launch Threads!` with the M8.C1k command line.
  - Scope: (1) find where `-M ze0` and the IPL feed the product info, area and SRAM backup today (`OALIoCtlGetProductInfo`, `GetBackUpFlashInfoTbl`, `RestoreSystemSramMain`, `Launcher [Area:…]`); (2) map those reads to offsets in the NAND/VFlash/SRAM dumps; (3) add an emulator option that serves them from the dump files (paths on the command line, nothing copied into the repository); (4) boot the EU card with the US data and record what the launcher does (area, map-code gate, map-DB gate, screen).
  - Input: EXP-2026-11-22-M8.C1k-unit-flash-nk1, `docs/hardware/head-unit.md`, M6.17/M6.19 notes on the SRAM area, `tools/qemu-ze0/`.
  - Done when: an EXP states which launcher gate the EU card hits with the US unit's data (or that it boots), with the serial lines and the dump offsets that decide it.
  - Stop: one session; vendor bytes, PIN, PROD content and screenshots stay out of the repository.
  - Falsifier: the launcher reads the area only from the card (no read from the dumps changes the outcome).
  - Claims: C-8350–C-8359

- [ ] **M8.C1n — UI layer on `-M ze0`: why InfoBar/UnitMainte/EvNotice create no window and what leaves `INI_STARTUP`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1l
  - Goal: Marek wants the UI layer in the emulator screenshot (2026-11-22). With `ze0_aui.py --object-store` every control registers and ScreenStateCC runs, but the screen state stays in `INI_STARTUP`. `NOTIFY_TRANSITION_FIRST_SCREEN` finds no window for InfoBarCC (46), UnitMainteCC (40) and EvNoticeCC (41), and 29 controls fail to initialise (C-8324, C-8325).
  - Precheck: run J16's configuration (`ze0_ipl.py patch --prefer-app auiapp.exe,auirtdll.dll --copy-dlls unitflash` + `ze0_aui.py --no-aui-timeout --skip-module-wait audio.exe --object-store`). The serial log shows `Filesystem pages = 592`, `Event[SK_OTH_STARTUP] Handled at State[INI_STARTUP]` and `The CC Window is not exist. [id = 46`.
  - Scope: (1) list the 29 failing controls by CLSID: break in auirtdll on the `Failed initialize control` path and read the control record; (2) for InfoBarCC, UnitMainteCC and EvNoticeCC, find the failing step of control init (window creation, shared buffer, IPC queue, missing import); (3) decode ScreenStateCC's transition table for `INI_STARTUP` and name the event that leaves it and who raises it; (4) raise it or fix the failing init in the guest as an emulator-only patch, and take a screenshot.
  - Input: EXP-2026-11-22-M8.C1l-object-store-registry, EXP-2026-11-22-M8.C1j-audio-activate, `tools/ze0_aui.py`.
  - Done when: a screenshot shows an AUI form element, or the EXP names the event that leaves `INI_STARTUP` with the ScreenStateCC table entry and the code that raises it.
  - Stop: one session; if the event is a vehicle signal over the micom/CAN, hand over to M8.H43–M8.H45 with the frame it needs.
  - Falsifier: the three CCs create their windows, and the state still does not change.
  - Claims: C-8340–C-8349

- [x] **M8.D1 — Decision gate after F1: continue to F2/F3?**
  - Status: done · Owner: task/m8.d1-decision-after-f1 · Critical: no · Pair: solo
  - Depends: — (trigger: M8 F1 stable kernel; see `todo-history-2026-11-05.md` §M8.D)
  - Goal: after F1, continue to F2/F3 only if L3 (M9) is blocked by runtime state, or an automatic regression loop without hardware is wanted; re-estimate F2–F4 and record the decision.
  - Precheck: `grep -c '^- \[x\] \*\*M8.B5 — Milestone F1' TODO.md` prints `1` (the trigger, F1, is reached).
  - Scope: the decision and the F2–F4 re-estimate, written into this block and the TODO critical path; no QEMU run, no code. The PO recommendation (critical path, "Decision due (Marek)") is input, not the decision.
  - Stop: the decision is Marek's; if no answer from him is on record, write the recommendation and re-estimate into this block and set `Status: blocked · Unblock: Marek (human decision)` instead of deciding.
  - Blocker: no answer from Marek on M8.D1 is on record — the pipe-free `grep -rniE -e 'marek.{0,80}\bF2\b' -e 'marek.{0,80}\bF3\b' -e 'marek.{0,80}M8\.D' docs/research/todo-history-*.md` exits 1, while the same search shape finds M6.14's recorded bench answer (`grep -n 'Marek decision: S0 is 1:1' TODO.md` prints it). F1 itself is reached (`grep -c '^- \[x\] \*\*M8.B5 — Milestone F1' TODO.md` prints `1`).
  - Unblock: Marek (human decision)
  - Recommendation (written for Marek; input, not the decision): **do not open F2 or F3 now.** No `Unblock:` line names F3, so F3 buys no map task; F4 (`M8.E4`) is the only L4 stage that unblocks anything (M4.51, M4.48, M8.E3) and it is the expensive one. Cheap order if Marek answers "continue":
    1. **F3 first: 1–2 weeks on the model path after C1** (was `2–4 weeks (HLE: ~1 week)`; HLE would throw `ze0-0008` away to save one week). The SD identification already runs (C-1462: CMD0…ACMD42); only ACMD13 over the HPB DMAC is left, and that is **M8.C1** (#394, draft). The DMAC is shared by `serial_scif`/`SDHC`/`wavessi*`, so it pays even if F3 stops. *Done when* a `\Storage Card`-style volume lists the map tree; deps C1, C10.
    2. **F2 only when a driver blocks the F3 boot: 2–4 weeks, unchanged.** 11 rows, none worked except C1/C2, which the `ze0-0008` patch already touches (C-1463); F2 loads `device.exe` drivers, it does not read a map file.
    3. **F4 only after M8.D2: 1–3 months, unchanged.** Nine rows; C4 micon + C5 CAN are the "unknown protocol" risk and C18 the display. It is the only stage that feeds the map tasks, through M8.E4.
    The automatic-regression-loop half of the Goal has no consumer today (no M9 task waits on F3); it pays only if a boot-run gate is wanted. Re-estimate: F2 `2–4 weeks` (unchanged), F3 `1–2 weeks` (was `2–4 weeks`, HLE `~1 week`), F4 `1–3 months` (unchanged).
  - Result: Marek decision 2026-11-21 (project thread): "Zrealizuj zatem DMA dla karty SD" = continue to F3 on the model path. F3 was reached the same day (M8.C1b, C-6875), in hours rather than the estimated 1–2 weeks. F2 as a separate stage was not needed.
  - Done when: the decision and its re-estimate are written down; no code change implied.
  - Claims: C-1590–C-1594

- [ ] **M8.D2 — Decision gate after F3: go to F4?**
  - Status: blocked · Owner: task/m8.d2-decision-after-f3 · Critical: no · Pair: solo
  - Depends: — (trigger: M8 F3 SD mounted; see `todo-history-2026-11-05.md` §M8.D)
  - Goal: after F3, go to F4 only if the micon/CAN handshake (M8.C4/C5) looks scriptable; F5 stays out of scope unless M8.C19 shows a simple frame-buffer path.
  - Precheck: `python3 tools/l4_status.py --run-log RUN.log` prints `F3    PASS` for a boot log of the F3 run (without a log every row is `NOT RUN`, i.e. the trigger is not reached and the gate is not due).
  - Scope: the F4 decision only, written into this block; inputs M8.C4/C5 (micon/CAN) and M8.C19 (frame buffer). No QEMU run, no code.
  - Stop: the decision is Marek's; without his answer on record, write the recommendation here and set `Status: blocked · Unblock: Marek (human decision)`.
  - Done when: the decision is written down; no code change implied.
  - Blocker (2026-11-21): the gate is not due — `python3 tools/l4_status.py --run-log RUN.log` prints `F3    NOT RUN` and `run log: none` (`summary: 0 PASS, 0 FAIL, 0 BLOCKED, 5 NOT RUN`), `grep -rl 'F3    PASS' docs/experiments archive dev_process | wc -l` prints `0`, and EXP-2026-11-20-M8.C10-sd-host says `F3 (the FAT partition mounted) is **not** reached` (next blocker M8.C1, HPB DMAC); in this `l4_status.py` revision F1–F4 are never scored from a log key (only F0 moves), so the literal `F3    PASS` is currently unreachable even with an F3 boot.
  - Unblock: Marek (human decision); the technical prerequisite is a real F3 boot log from the peripheral chain (its next row is the HPB DMAC), which no board block can create yet
  - Recommendation (for Marek; the decision is his, EXP-2026-11-21-M8.D2-decision-after-f3):
    - **F4: conditional yes, only after F3.** `full-system-emulation.md` §4 prices F4 at 1–3 months with "unknown micon protocol; graphics init; watchdogs", so the F4 entry test is exactly this gate's test: M8.C4 (micon/power: ACC/ignition, "system ready") and M8.C5 (CAN: register block vs sub-micon, the frames `CAN.dll` waits for) must reduce to a finite, scripted handshake. Neither row exists on the board yet (`M8.C` is one open umbrella, `grep -c '^- \[ \] \*\*M8.C —' TODO.md` prints `1`; only C10 is done), so the test cannot be answered today.
    - **F5: no.** §6 item 5 says "Do not plan for F5"; F5's only candidate frame-buffer path is M8.C19 (unstarted, area 4 undocumented), and the gate forbids F5 unless C19 shows a simple frame-buffer path. Visual acceptance stays on the bench.
    - **Cheaper alternative while F3 is blocked:** §5's table already gives L3 the per-function answers F4 would give in context, so F4 is worth its months only for the boot-ordered file-access log and the `HDD_INFO` decision in situ (M8.E4) — not for format coverage.
  - Result: EXP-2026-11-21-M8.D2-decision-after-f3; C-1595–C-1599. Negative gate record: trigger not reached, recommendation above, `blocked` on the F3 log.
  - Claims: C-1595–C-1599
  - Note: 2026-11-21: the gate is due — F3 is reached (M8.C1b, C-6875; `ze0_sdhost.py serial` prints `store_ready 1`, `part_mounted 2`; `l4_status.py` still scores only F0 from a log). Marek the same day asked for the next two steps (launcher `VerInf`/`Error Proc<00000050>` = M8.C1c, serial DMA = row C2) and for the move to QEMU 11.1.3 (M8.A11); the F4 decision itself (micon/CAN) is still his.

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


- [ ] **M8.E3 — Dump loaded process images** (`Navi.exe` + DLLs after init)
  for L3.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.E4
  - Precheck: `grep -c '^- \[x\] \*\*M8.E4 ' TODO.md` prints `1` (an emulated boot that loads `Navi.exe` exists), and `python3 tools/l4_status.py --run-log RUN.log` prints `F4    PASS` for that boot.
  - Scope: the process images of `Navi.exe` and its DLLs after init, read out of one QEMU `-M ze0` boot (EU2011 IMG256) into `archive/work/` (vendor-derived, never committed); the repo gets only the dump tool, VA ranges, sizes and SHA-256s. Not: US2011, other processes.
  - Stop: if F4 is not reached, stay `open`/`blocked` on M8.E4; if the dump differs from `nk_decomp.py`'s decoded sections in more than the IAT/BSS ranges `va_class.py` names, record the diff in an EXP instead of feeding the dump to L3.
  - Claims: C-1620–C-1629

- [ ] **M8.E4 — Full `Navi.exe` on a generated card (F4 acceptance run)**
  - Status: open · Owner: — · Critical: no
  - Depends: F4 (`Navi.exe` headless, M8.D1/D2 gates), M9.16
  - Goal: the strongest software check before the car: boot the emulated
    unit with a card image and log every map file `Navi.exe` opens and
    every error screen it raises.
  - Done when: the factory US image and the S2 image both reach the map
    state with no error screen, with the file-open logs compared in an EXP.
  - Precheck: `python3 tools/l4_status.py` lists `F4 BLOCKED (M8.A3, M8.A6, M9.16)`; the run is possible only once `grep -cE '^- \[x\] \*\*M9.16 ' TODO.md` prints `1` and a boot log gives `F3    PASS` (`python3 tools/l4_status.py --run-log RUN.log`).
  - Scope: one QEMU `-M ze0` boot per card image (factory US2011 card, S2 card) to the map state, with the `Navi.exe` file-open log; the logs and screenshots stay in `archive/work/` (vendor-derived). Not: F5 (screen) beyond detecting an error screen, the car.
  - Stop: if a boot stops short of the map state twice with the same log, record the last opened file and the stage in an EXP and set `blocked` on the M8.C row or M9.16 step that stops it.
  - Claims: C-2270–C-2279

- [ ] **M8.G1 — Hardware of the three generations: ZE0 (2011–12, `X210`) vs AZE0 (2013–17, `X212`) vs ZE1 / Leaf 2 (2018+), from our images**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: map
  - Priority: low (Marek, 2026-11-22: the ZE0 2011 unit stays the focus; the other generations are the long-term goal "run any of them in QEMU").
  - Depends: M1.36 (done), M1.39 (done); M1.38 and M1.37 help
  - Goal: Marek asks how the later units differ in hardware. Fill a per-generation table: CPU/SoC (BSP and platform strings), RAM size and map (ROMHDR RAM windows), NOR/NAND flash and flash driver (`fmmdrv` vs `fmmdrv_05`/`_07`, `FlashManager2`), display (resolution, DU/2DG vs DirectDraw), audio, Bluetooth, CAN sub-microcontroller, USB host (`UsbConMngCC.dll`), telematics (`Telema*`), camera, Wi-Fi if any, OS (CE version/build).
  - Precheck: `python3 tools/cerom.py --image-start 0x3e00200 <EU2014 head> romhdr` prints a ROMHDR; note which ZE1 images exist: the only post-2016 image we hold is `ENV200_2019_25920-6WX1C-EUR.img` (e-NV200, QY8x, `CLA-NAVI06-01`, C-123), which is **not** a Leaf 2 unit; say whether it is the same board family or record "no ZE1 image" and what image would be needed.
  - Scope: static only, from the EU2011, US2011, EU2014, EU2016 and 2019 images plus `docs/hardware/head-unit.md`. For each row give the evidence (string, module, VA) or `unknown`. First step for the 2019 image: is it still WinCE on SH-4 at all (`cerom.py` / file magic / ELF or Linux kernel strings)?
  - Input: EXP-2026-11-20-M1.36-module-census-4-images, `docs/hardware/head-unit.md`, `docs/research/image-versions.md`, `tools/cerom.py`, `tools/rom_atlas.py` if merged.
  - Done when: `docs/hardware/generations.md` has the table with one column per generation (ZE0 / AZE0 / ZE1-or-QY8x), every cell with evidence or `unknown`, and an EXP lists the three biggest differences that matter for emulation.
  - Stop: do not open or change any card; if the 2019 image is not CE/SH-4, record the architecture and stop that column there.
  - Falsifier: the EU2014 kernel ROM names the same BSP string and RAM window as EU2011 (then AZE0 is a board revision, not a new platform).
  - Claims: C-6940–C-6949

- [ ] **M8.G2 — Plan: one QEMU machine type per generation (`ze0`, `aze0`, `ze1`), shared parts vs differences**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: plan
  - Priority: low (after the ZE0 F5 screen, M8.C1f).
  - Depends: M8.G1
  - Goal: Marek expects separate machine types for the different card images (2026-11-22). Decide which devices of `-M ze0` are reused (SH-4A CCN/INTC/TMU, HPB-DMAC, SDHC, SCIF, loader, `ipl-patch`) and which need a new model per generation, so that `-M aze0` (X212 cards 2014/2016) and later `-M ze1` are added as machines in the same out-of-tree patch series. **Constraint: we keep a patch series on QEMU 11.1.3 (M8.A11), not a fork; the plan must not change that.**
  - Precheck: `ls tools/qemu-ze0/patches/` lists the `ze0-00NN` series; M8.G1 table exists.
  - Scope: a design doc only, no QEMU code. For each device: shared / parameterised (property on one machine class) / new; the machine-class layout (one `TYPE_ZE0_MACHINE` base with per-generation subclasses vs separate files); what the X212 kernel needs first to reach F0 (boot log) on `-M aze0` with today's devices.
  - Input: M8.G1 output, `tools/qemu-ze0/patches/README.md`, `docs/research/full-system-emulation.md`, EXPs of M8.A3/A9/A11/C1b–C1e.
  - Done when: `docs/research/qemu-machine-types.md` has the device × generation table and an ordered list of follow-up tasks (one per new device model, each with a Done when), and the first of them (`-M aze0` F0 on the EU2014 kernel) is added to this board with `board.py add-task`.
  - Stop: if M8.G1 shows ZE1 is not SH-4/CE, plan `aze0` only and mark `ze1` as a separate emulator decision for Marek.
  - Falsifier: an F0 try of the EU2014 kernel on unmodified `-M ze0` prints the same boot log as EU2011 (then no new machine is needed for AZE0, only properties).
  - Claims: C-6950–C-6959

- [ ] **M8.G3 — Why does Android Auto run on AZE0 units and not on ZE0? (H.264 decode, USB host, CPU, OS)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: research
  - Priority: low (curiosity of Marek, 2026-11-22; also tells whether the ZE0 unit could ever do phone projection).
  - Depends: M8.G1 (helps; can start in parallel)
  - Goal: people get Android Auto working on AZE0 head units but not on ZE0. Find out what the ZE0 unit lacks. Marek's hypothesis: the phone stream is H.264 and needs a hardware video decoder. Check also: USB host mode and Android Open Accessory support, CPU headroom for software decode at 800 × 480, Wi-Fi, OS/CE version and codec libraries, the existing projection-like modules on X212 (`UsbConMngCC.dll`, `Celavi*`, `Telema*`, DirectDraw).
  - Precheck: `python3 tools/cerom.py` lists modules of EU2011 and EU2014 ROM A/B/C.
  - Scope: (1) public sources on how AZE0 owners run Android Auto (which unit, which firmware, aftermarket box or native app); record URLs in `docs/research/sources.md`. (2) Static search of all four images for H.264/AVC/VPU/codec/DirectShow/AOAP/`accessory` strings and drivers, per generation. (3) USB: the ZE0 OHCI block at `0xffe70400` (C-6415, HYPOTHESIS) vs an EHCI/OTG controller on X212. (4) A verdict per hypothesis: confirmed / refuted / unknown, with evidence.
  - Input: EXP-2026-11-20-M1.36-module-census-4-images, `docs/hardware/head-unit.md`, M8.G1 table.
  - Done when: an EXP `EXP-…-M8.G3-android-auto-ze0-vs-aze0` with the per-hypothesis verdict table and the answer to "what does the ZE0 unit lack", each row citing a source URL or an image string/module.
  - Stop: no flashing or card change; if public sources say the AZE0 solution is an external box (video over a separate input), record that and stop the codec search.
  - Falsifier: an H.264 decoder module or VPU driver is found in the ZE0 2011 ROMs too (then the decoder is not the reason).
  - Claims: C-6960–C-6969
  - Note: Marek, 2026-11-22: lead https://www.youtube.com/watch?v=BO-hEO0uR3A (not opened from the Claude sandbox, youtube.com is blocked). Russian groups once distributed modified SD card images that unlocked Android Auto on AZE0, so the feature is probably present in the AZE0 firmware and only switched off. First check: compare such an image (if Marek finds one) with the factory EU2014/2016 card: which ROM A module or registry/config byte differs. Do not commit vendor bytes.

- [x] **M8.H1 — Every serial channel of `-M ze0` is a named host chardev, RX and TX**
  - Status: done · Owner: task/m8.h1-serial-chardevs · Critical: yes · Pair: required
  - Step: model
  - Depends: M8.C1e (done), M8.C2a (done)
  - Goal: Marek wants to feed GPS positions and touch input into the emulator (2026-11-22). GPS (`SCI7:`), the display unit (`SCI3:`), the audio microcontroller (`SCI1:`), Bluetooth (`SCI8:`) and the VCAN microcontroller (`UAT3:`) all sit behind serial lines (`docs/hardware/head-unit.md`), so one patch that connects each line to a host chardev lets every chip model live outside QEMU as a Python peer (`docs/research/qemu-connectors.md`). Today only channel-10 DMA TX to SCIF1 reaches the host (`ze0-0011`), and SCIF 0–9 are stubs (`ze0-0013`).
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) writes the audio frame of EXP-2026-11-22-M8.C2a-serial-dma to the SCIF1 log and receives nothing; `grep -c chardev tools/qemu-ze0/patches/ze0-0011-hw-sh4-ze0-serial-dma.patch` shows what exists.
  - Scope: one patch `ze0-h01-serial-chardevs.patch`: a machine property per line (`sci0`…`sci8`, value = chardev id) for SCIF 0–8, TX and RX, through the path each driver really uses (FIFO interrupt or HPB-DMAC channel, read from `serial_scif.dll`); a line without a chardev keeps today's stub behaviour. `run.sh --serial-peer sci7=unix:PATH`. The external UARTs (`UAT3:`/`UAT4:`) are M8.H3, not here.
  - Input: `ze0-0011`, `ze0-0013`, EXP-2026-11-22-M8.C2a-serial-dma, `tools/ze0_serial.py`, `docs/hardware/head-unit.md` (port table), `tools/sh4dis.py`.
  - Done when: a host script on the `sci1` socket receives the frame the guest sends, and a reply written by the script is read by the guest driver (its receive path runs: breakpoint or DBGMSG line named in the EXP); the same loop-back passes on `sci7`; with no `--serial-peer` the serial log and boot stage equal the baseline run. `tools/ze0_serial.py --selftest` covers the socket framing. EXP + claims.
  - Stop: if RX needs a second DMA engine or an interrupt source that is not modelled, land TX for all lines, name the missing piece per line and stop.
  - Falsifier: bytes written to the socket never reach the driver's read buffer although the RX interrupt (or DMA end) is delivered.
  - Claims: C-6980–C-6989
  - Result: EXP-2026-11-22-M8.H1-serial-chardevs; sci1+sci7 TX/RX loopback, ch7 ISR 1 hit, baseline unchanged, gate 5/5

- [ ] **M8.H2 — `serial_uat.dll`: which UART chip sits at `0x19b00000`–`0x19e00000` (register map, interrupts)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: `UAT3:` carries the vehicle CAN microcontroller (`CAN.dll`), `UAT4:` has no known user. Nothing models the external UARTs, so no CAN frame can enter the emulator. Read the driver and write the register model a QEMU device needs.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --image-start 0x3e00200 --encoding all UAT3:` prints at least one module; `python3 tools/nk_decomp.py pdata archive/head256.img --module serial_uat.dll VA` answers for the init entry.
  - Scope: static only, EU2011 build B/A: register offsets and widths the driver reads/writes, the interrupt (SYSINTR and INTEVT), baud divisor writes, FIFO depth, and the verdict `16550-compatible` (then QEMU's `serial-mm` fits) or a list of differences. No QEMU code.
  - Input: `tools/cerom.py`, `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/ce_drivers.py`, `docs/research/rom-registry.md`, `docs/hardware/head-unit.md`.
  - Done when: `docs/firmware/serial-uat.md` has the register table with a VA per row and the 16550 verdict; `python3 tools/fn_audit.py` passes with the new VAs; EXP + claims; `docs/hardware/head-unit.md` rows `UAT3:`/`UAT4:` updated.
  - Stop: one session; if the driver is a thin wrapper over a kernel IOCTL, name the kernel routine and stop.
  - Falsifier: the driver touches no address in `0x19b00000`–`0x19e00000` (then the address range in the hardware map is wrong).
  - Claims: C-6990–C-6999

- [ ] **M8.H3 — External UART model on `-M ze0`: `UAT3:` and `UAT4:` as host chardevs**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.H2
  - Goal: With the register map of M8.H2, add the two external UARTs so the VCAN peer (M8.H50) can talk to `CAN.dll`.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` lists accesses in `0x19b00000`–`0x19e00000` (the driver probes an absent chip).
  - Scope: patch `ze0-h03-ext-uart.patch`: QEMU `serial-mm` (or a small device if M8.H2 says the chip differs) at the addresses and interrupt of M8.H2, properties `uat3`/`uat4` = chardev id; `run.sh --serial-peer uat3=…`.
  - Input: `docs/firmware/serial-uat.md` (M8.H2), `ze0-0003` (INTC), `tools/qemu-ze0/README.md`.
  - Done when: a byte written by a host script to the `uat3` socket is returned by the guest driver's read, and the bytes `CAN.dll` writes at start appear on the socket; baseline boot unchanged without the property. EXP + claims.
  - Stop: if the chip needs a bus (CS/wait-state) register that is not modelled, record it and stop.
  - Falsifier: `CAN.dll` opens `UAT3:` successfully before the patch (then the driver did not need the chip).
  - Claims: C-7000–C-7009

- [ ] **M8.H4 — The guest screen as a QEMU display surface (`screendump`, VNC, `-display gtk`)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.C1f
  - Goal: `tools/ze0_screenshot.py` copies VRAM with `pmemsave` and composes the planes on the host. A real QEMU console gives `screendump`, VNC and a live window for free, and is the base for mouse-to-touch (M8.H40).
  - Precheck: after M8.C1f, `tools/ze0_screenshot.py grab` returns a non-black 800 × 480 frame from a running guest.
  - Scope: patch `ze0-h04-display-surface.patch`: `ze0-gfx` registers a graphic console and composes the DU planes the way `ze0_screenshot.py` does (same plane order, RGB565); `run.sh --display SPEC` and `--vnc`. No new drawing commands (that is M8.C1f).
  - Input: `ze0-0013`, the M8.C1f patch, `tools/ze0_screenshot.py`, EXP-2026-11-22-M8.C1e-display-engine.
  - Done when: HMP `screendump FILE` and `ze0_screenshot.py grab` of the same instant give the same image (pixel hash equal, compared by a command in the EXP); `-display none` runs stay unchanged.
  - Stop: if plane blending needs alpha rules not yet known, show the top opaque plane only and record the rest.
  - Falsifier: the console image differs from the host-composed one on a static screen.
  - Claims: C-7010–C-7019

- [ ] **M8.H5 — Start in seconds: `savevm` after boot and `run.sh --loadvm`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.C1e (done)
  - Goal: A boot to the idle UI takes minutes of host time (card mount about 170 s; launcher threads far longer while the audio microcontroller is absent — project notes of 2026-11-22). Every L4 experiment pays that. A snapshot taken at idle makes each later run start from it.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) reaches the launcher line `Finish Launch Threads`; HMP `savevm t1` on that run either works or names the device that has no `vmstate`.
  - Scope: `VMStateDescription` for the `ze0` devices that lack one (INTC/TMU glue, SD host, HPB-DMAC, `ze0-gfx`, unit record), as patch `ze0-h05-vmstate.patch`; `run.sh --savevm NAME --at-log REGEX` and `--loadvm NAME`; the qcow2 overlay holds the snapshot (`tools/qemu-ze0/mkoverlay.py`).
  - Input: `tools/qemu-ze0/patches/`, `tools/qemu-ze0/mkoverlay.py`, `tools/qemu-ze0/run.sh`.
  - Done when: a run started with `--loadvm` continues: the guest keeps printing/serving (a serial or DBGMSG line after load, or a VRAM hash that equals the one taken before `savevm`), and reaches that point in under 30 s of wall time; the EXP quotes both wall times from the commands.
  - Stop: if one device cannot be saved without a redesign, record which one and deliver the snapshot for the rest only if the guest survives a load; otherwise blocked.
  - Falsifier: after `loadvm` the guest hangs or faults at the first interrupt (state missing).
  - Claims: C-7020–C-7029

- [x] **M8.H6 — Determinism: two boots with `-icount` give the same log and the same screen**
  - Status: done · Owner: task/m8.h6-run-determinism · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1e (done)
  - Goal: An L4 regression gate needs repeatable runs. Measure whether two identical boots are bit-identical in what we compare (serial log, DBGMSG log, SD read order, VRAM hash at a fixed guest time), and name each source of difference.
  - Precheck: `bash tools/qemu-ze0/run.sh --help` lists `--icount`; the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) runs twice on this host.
  - Scope: measurement and, where cheap, a fix (fixed RTC base, `-icount shift=0,sleep=off`, no host-time device). New `tools/ze0_rundiff.py A B` compares two run directories and prints the first difference per channel, with `--selftest`.
  - Input: `tools/qemu-ze0/run.sh`, `tools/ze0_dbgmsg.py`, `tools/ze0_sdhost.py`, `tools/ze0_screenshot.py`, `tools/qemu_boot_cmp.py`.
  - Done when: `python3 tools/ze0_rundiff.py RUN1 RUN2` exits 0 for two fresh runs, or the EXP lists every channel that differs with its cause; `ze0_rundiff.py --selftest` passes and is in `tools/selftest.py`.
  - Stop: one session of measurement; do not rewrite device models for determinism here.
  - Falsifier: the runs differ with `-icount` on and no host-clock device in the machine.
  - Claims: C-7030–C-7039
  - Result: EXP-2026-11-22-M8.H6-run-determinism; ze0_rundiff E/F exit 0 (4/4 channels), G/H exit 0; C-7030-C-7039

- [x] **M8.H7 — `tools/ze0_ui.py`: a scenario runner for L4 (wait, tap, key, position, screenshot, expect)**
  - Status: done · Owner: task/m8.h7-ui-scenario · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: L4 tests should be files, not shell history. A scenario is a list of steps (`wait-log REGEX`, `sleep-guest S`, `tap X Y`, `key NAME`, `gps LAT LON`, `shot NAME`, `expect-hash NAME SHA`), run against QMP and the peer sockets of `docs/research/qemu-connectors.md`.
  - Precheck: `python3 tools/ze0_screenshot.py --help` works (the screenshot step reuses it).
  - Scope: the runner, its step grammar, a fake QMP/peer server for `--selftest`, and exit codes (0 pass, 1 expectation failed, 3 nothing runnable — SKIP is never PASS). `tap`/`key`/`gps` call the peers when they exist and fail with exit 3 when not. No live guest needed for done.
  - Input: `tools/ze0_screenshot.py`, `tools/qemu-ze0/run.sh` (monitor socket), `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_ui.py --selftest` passes (in `tools/selftest.py`), including one negative control (a wrong `expect-hash` exits 1) and the exit-3 path; `docs/format/ze0-tools.md` or the tool README documents the grammar.
  - Stop: one session.
  - Falsifier: a scenario with a failing expectation exits 0.
  - Claims: C-7040–C-7049
  - Result: EXP-2026-11-22-M8.H7-ui-scenario; ze0_ui selftest 20/20, wrong-hash exit 1, exit-3 paths, real boot 3 steps exit 0

- [x] **M8.H8 — Which card files does the firmware read, and where: SD block trace mapped to file and offset**
  - Status: done · Owner: task/m8.h8-sd-trace · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M8.C1b (done)
  - Goal: Rule 13 wants every generated format confirmed by the firmware. At L4 the cheapest witness is the SD read stream: map every block the guest reads to (file, offset) through the FAT of the card, so one boot tells which map files and which byte ranges `Navi.exe` actually consumes.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) mounts the card (F3) and `python3 tools/ze0_sdhost.py serial W/serial.log` reports transfers.
  - Scope: new `tools/ze0_sdtrace.py`: input = a block-read log of the SD model (QEMU `-trace 'sdcard_read_*'`, or the DMAC transfer log `ze0_sdhost.py` already parses) + the card image; output = per-file read ranges in time order, a per-file coverage table, JSON. Synthetic FAT fixture for `--selftest`. Then one EU2011 boot to idle.
  - Input: `tools/ze0_sdhost.py`, `tools/leafimg.py`/`tools/mkcard.py` (FAT reading), `tools/cardcheck.py`, `docs/format/sd-card-layout.md`.
  - Done when: `python3 tools/ze0_sdtrace.py RUNDIR --card CARD --json` lists, for the EU2011 boot, every file opened under the map tree with byte ranges (expected at least `MMAIN001.DAT`, `DRSTR001.DAT`, `CMP.LST` — if one is missing, that is a finding); `--selftest` passes; the EXP compares the list with the L3 mount (`tools/datask_l3.py mount`). Row updates in `docs/research/reader-coverage.md` column F4 where a file is seen.
  - Stop: if block reads cannot be attributed (cache layer reads whole clusters ahead), report cluster-level ranges and say so.
  - Falsifier: the trace shows no read of any map file although the UI reaches idle (then the map loads lazily and the scenario needs a position: M8.H31).
  - Claims: C-7050–C-7059
  - Result: EXP-2026-11-22-M8.H8-sd-block-trace; 14 files, 10523 reads / 7174 mapped, selftest 17/17, L3 overlap 6/7

- [ ] **M8.H9 — Function coverage at L4 with a TCG plugin (no QEMU patch): which `Navi.exe` functions ran**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.C1d (done)
  - Goal: Know which readers execute in a scenario without setting breakpoints: a TCG plugin records executed block addresses; the host maps them to function starts (`.pdata`) per module.
  - Precheck: `tools/qemu-ze0/build.sh --dry-run` shows the configure line; QEMU 11.1.3 has `--enable-plugins` (check `configure --help` in the unpacked tree).
  - Scope: `build.sh --plugins` (configure flag only, no source patch), a plugin source under `tools/qemu-ze0/plugins/` (built against the QEMU plugin API, out of tree), and `tools/ze0_cov.py RUN --module Navi.exe` → executed functions, counts, and a diff of two runs. Address-space note: modules run in place, so guest VA → module is `tools/cerom.py` data. `--selftest` on a synthetic trace.
  - Input: `tools/qemu-ze0/build.sh`, `tools/nk_decomp.py pdata`, `tools/pdata.py`, `tools/callgraph.py`, `tools/cerom.py`.
  - Done when: one EU2011 boot with the plugin; `python3 tools/ze0_cov.py RUN --module Navi.exe --json` prints the executed-function count and contains the located readers that must run at mount (`MMAIN001` reader, `DRSTR` parser — VAs in `docs/research/reader-coverage.md`); a function known not to run (the `POINT` walker before any search) is absent — the negative control. EXP + claims.
  - Stop: if plugins cost more than 5× run time, sample (every Nth block) and say so.
  - Falsifier: the mount-time readers located at L3 are absent from the L4 coverage (then L3 and L4 disagree on the path — a finding for M9).
  - Claims: C-7060–C-7069

- [ ] **M8.H10 — Which bytes of a tile does the firmware touch: read-watch on the tile buffer at L4**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.H8, M8.H9
  - Goal: `tile_bytes` in `tools/map_signals.py` counts bytes our docs explain. The firmware can say which bytes it reads: watch the buffer that receives a tile and record read offsets with the reading PC.
  - Precheck: M8.H8 names the SD read that loads a tile and M8.H9's plugin builds; `python3 tools/read_watch_l3.py --help` works (the L3 form of the same idea).
  - Scope: extend the M8.H9 plugin with memory-read callbacks limited to one guest buffer (address from the DMA destination of the tile read), output offset → PC → function; one factory tile at the default position. Compare with the L3 read-watch of the same tile.
  - Input: `tools/read_watch_l3.py`, `tools/ze0_sdtrace.py` (M8.H8), `tools/ze0_cov.py` (M8.H9), `docs/format/map-tiles.md`.
  - Done when: an EXP table: tile, bytes read / bytes total per section, top reading functions, and the list of byte ranges read by the firmware but not explained in `docs/format/map-tiles.md`; the L3 comparison is one row (same / different, with counts).
  - Stop: if the tile is decompressed into a second buffer, follow one hop (the decompressor's output) and stop there.
  - Falsifier: no read falls inside the buffer after the tile is loaded.
  - Claims: C-7070–C-7079

- [ ] **M8.H11 — L3 against L4: the `MMAIN001` reader and the `DRSTR` parser return the same values in both**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.C1d (done)
  - Goal: Every L3 verdict assumes the harness runs the function the way the unit does. Check it once on the two readers that certainly run at mount: break at their entry and exit in the full system, dump arguments and outputs, and compare with the L3 targets.
  - Precheck: `python3 tools/mmain_l3.py --help` and `python3 tools/drstr_l3.py --help` work; `bash tools/qemu-ze0/run.sh --help` lists `--gdb`.
  - Scope: EU2011, EU card. Breakpoints at the reader VAs of rows 3 and 4 of `docs/research/reader-coverage.md` via the gdbstub (`tools/qemu-ze0/gdb-ze0.py`); new `tools/ze0_l3parity.py` drives it and prints a field-by-field comparison with the L3 output.
  - Input: `tools/mmain_l3.py`, `tools/drstr_l3.py`, `tools/qemu-ze0/gdb-ze0.py`, `docs/research/reader-coverage.md`.
  - Done when: `python3 tools/ze0_l3parity.py --target mmain --target drstr …` prints `same` for every compared field or lists the differing ones; the EXP states the verdict per target and updates the F4 column of rows 3 and 4.
  - Stop: if a breakpoint is never hit, record the coverage evidence (M8.H9 if merged) and stop.
  - Falsifier: a field differs between L3 and L4 on the same card (then the L3 preconditions are wrong for that target).
  - Claims: C-7080–C-7089

- [ ] **M8.H12 — The US 2011 card on `-M ze0` (Marek's unit is US)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.C1d (done)
  - Goal: All L4 work so far used the EU 2011 card. The only real unit is US, and its card carries another `Navi.exe` build (rule 14, name the build). Bring the US card to the same stage.
  - Precheck: `python3 tools/fetch_image.py --image US256 -o archive/us256.img` verifies; `python3 tools/ze0_ipl.py patch archive/us256.img -o ipl-us.txt` runs or names the constant that differs.
  - Scope: US2011: `verinf`/`mapdb` values for the US card (read as in EXP-2026-11-22-M8.C1c-launcher-verinf), the `ipl-patch` for the US image, one boot with the US card behind an overlay. Record every address in the recipe that is build-specific.
  - Input: `tools/ze0_ipl.py`, EXP-2026-11-22-M8.C1c-launcher-verinf, EXP-2026-11-22-M8.C1d-multi-xip, `tools/fetch_image.py --image US`.
  - Done when: one US boot reaches the same launcher stage as EU (`Finish Launch Threads` or the named later stage), with the command line in the EXP and `tools/qemu-ze0/README.md` gaining a US row; or the first US-only blocker is named with its log line.
  - Stop: two sessions; a US-only crash inside `Navi.exe` is recorded, not debugged here.
  - Falsifier: the EU recipe works unchanged on the US card with EU constants (then nothing is build-specific and the README says so).
  - Claims: C-7090–C-7099

- [x] **M8.H13 — `tools/l4check.py`: one command, card image in, L4 verdict out**
  - Status: done · Owner: — · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M8.C1d (done)
  - Goal: L1–L3 have one-command gates; L4 is a recipe in EXP records. Wrap the boot into a gate: stage reached (F0…F5 names of `tools/l4_status.py`), launcher verdict on the card, map files opened, time to idle.
  - Precheck: `python3 tools/l4_status.py --help` works; the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) runs by hand.
  - Scope: `tools/l4check.py --card IMG [--head IMG256] [--qemu BIN] [--json]`: builds the overlay, the `ipl-patch`, derives `verinf`/`mapdb`, runs, parses serial/DBGMSG logs into a verdict; exit 0 pass, 1 fail, 3 not runnable (no QEMU binary or no image — never a pass). `--selftest` on canned logs.
  - Input: `tools/qemu-ze0/run.sh`, `tools/qemu-ze0/mkoverlay.py`, `tools/ze0_ipl.py`, `tools/ze0_dbgmsg.py`, `tools/ze0_sdhost.py`, `tools/l4_status.py`.
  - Done when: `python3 tools/l4check.py --card EUCARD --json` exits 0 with the stage reached on the factory card; the same command on a card with a wrong volume label or a truncated `MMAIN001.DAT` (built with `tools/imgpatch.py`) exits 1 and names the stage that failed; `--selftest` in `tools/selftest.py`; `docs/research/feedback-loop.md` L4 paragraph points to it.
  - Stop: if no log line separates 'card accepted' from 'card rejected', report the two logs side by side and stop.
  - Falsifier: the broken card and the factory card give the same verdict.
  - Claims: C-7100–C-7109
  - Result: EXP-2026-11-22-M8.H13-l4check; factory exit 0 stage F5 idle 218.62 s, broken card exit 1 stage F4, gate 5 pass / 0 fail / 0 skip

- [ ] **M8.H14 — CI: every push checks that the `ze0` patch series still applies**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: The series is 13+ patches and several agents will add more in parallel. A patch that no longer applies after a merge is found today only by the next person who builds.
  - Precheck: `tools/qemu-ze0/build.sh --check-version 11.1.3` exits 0 locally; `.github/workflows/` has no job that calls it (`grep -rc check-version .github/workflows`).
  - Scope: one workflow job: cache the pinned tarball by its SHA-256, run `build.sh --check-version 11.1.3` and `build.sh --selftest`; no build, no vendor image. Patch naming rule of `docs/research/qemu-connectors.md` checked by a small lint (`ze0-NNNN-` or `ze0-hNN-`, unique numbers).
  - Input: `tools/qemu-ze0/build.sh`, `.github/workflows/ci.yml`.
  - Done when: the job is green on the PR; a deliberately broken hunk on a scratch branch makes it red (run id in the EXP); `build.sh --selftest` covers the lint.
  - Stop: if GitHub runners cannot reach `download.qemu.org`, use the gitlab tag fallback of `build.sh`, else blocked with the error.
  - Falsifier: the job stays green with a patch that does not apply.
  - Claims: C-7110–C-7119

- [ ] **M8.H15 — Turn on the firmware's own debug output: debug zones of `Navi.exe` and the drivers**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1d (done)
  - Goal: `ze0-0007` hooks the kernel debug message path, but retail modules print little. CE modules carry `dpCurSettings` zone masks (and often a registry override). Find how to enable them for `Navi.exe` map modules, `SDHC.dll`, `navdrv.dll`, `lcddrv.dll`, so a boot log names file opens, positions and errors in the vendor's words.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all DebugZones` and a search for `dpCurSettings`-shaped data (module name string followed by 16 zone names) return candidates; `python3 tools/ze0_dbgmsg.py --help` works.
  - Scope: static: per module, where the zone mask lives (data VA, default value) and whether a registry value overrides it (`tools/cehive.py` on the hives). Runtime: set one mask through `ipl-patch` or a gdb write and count new DBGMSG lines.
  - Input: `tools/ze0_dbgmsg.py`, `tools/cehive.py`, `tools/va_class.py`, `tools/ze0_ipl.py`, EXP-2026-11-20-M8.E2-registry-loaded.
  - Done when: an EXP table module → zone mask VA → default → lines gained when set (measured in one boot per module, at least three modules, one of them a map-data module); `run.sh --debug-zones FILE` or an `ipl-patch` fragment makes it one option.
  - Stop: if the retail build compiled the messages out (no format strings behind the zones), say so with the string census and stop.
  - Falsifier: setting the mask adds no line for any module.
  - Claims: C-7120–C-7129

- [ ] **M8.H16 — Boot the test-mode kernel (ROM image C) on `-M ze0`: the service screens as a test bench for the models**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1d (done)
  - Goal: Image C is the kernel with `TestMode.exe` (hardware checks for GPS, touch, CAN, audio, SD). Its screens and logs would validate each peer model against the vendor's own diagnostics, and it has the `AppTimerDll` that `Speech.exe` misses on image B.
  - Precheck: `python3 tools/cerom.py --image-start 0x5200200 archive/head256.img romhdr` prints the ROMHDR of C; `python3 tools/ze0_ceload.py plan --help` shows `kernel-off`.
  - Scope: EU2011: boot with `kernel-off=0x5200200`, the `ipl-patch` variant for C (how the IPL selects C on the unit: `tools/kernel_select.py`), log to the first blocker. Static list of the test items `TestMode.exe` offers and which device each talks to.
  - Input: `tools/kernel_select.py`, `tools/ze0_ipl.py`, `tools/ze0_ceload.py`, EXP-2026-11-05-M2.10-testmode.
  - Done when: an EXP with the boot log stage reached under C and the table test item → driver/port → peer task in this board (M8.H27…H62); or the named blocker.
  - Stop: two sessions.
  - Falsifier: C boots exactly like B with no extra process (then test mode is entered another way and the EXP says which).
  - Claims: C-7130–C-7139

- [ ] **M8.H17 — Second SD slot on `-M ze0` (`DSK8:`, `\UserSD`)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1b (done; SD host row C10 of the peripheral table is done too)
  - Goal: The unit has a second slot for user media. With it a test can offer the firmware an update or a user file without touching the map card.
  - Precheck: the `ze0-0008` patch header names port 1 (`0xffe4d000`); the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) logs the port-1 probe.
  - Scope: `run.sh --sd2 FILE`: second `sd-card` on SD host port 1 with its DMAC channel; card-detect off when absent (today's behaviour).
  - Input: `ze0-0008`, `ze0-0009`, `tools/ze0_sdhost.py`.
  - Done when: with a small FAT image on port 1 the guest mounts a second volume (log line or a file read seen by `ze0_sdhost.py`); without `--sd2` the boot log equals the baseline.
  - Stop: if port 1 uses a DMA channel the model lacks, record its number and stop.
  - Falsifier: the guest never issues a command on port 1 even with card-detect asserted.
  - Claims: C-7140–C-7149

- [ ] **M8.H18 — NOR flash (`FMD1:`) backed by a host file: settings and user data survive a restart**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.C1c (done)
  - Goal: The board has 8 MiB NOR with the product record, 'SRAM' user data and 'VFlash' (`docs/hardware/head-unit.md`). `ze0-0010` answers the product-record query only. A file-backed flash lets a test seed the last position, destinations and language, and lets a shutdown persist them.
  - Precheck: `grep -n 'flash\|FMD' tools/qemu-ze0/patches/ze0-0010-hw-sh4-ze0-unit-record.patch` shows what is modelled; the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` shows whether `flash.dll`/`FlashManager.dll` touch an unmodelled window.
  - Scope: static: how `flash.dll` reaches the chip (window address, CFI or vendor commands, block map of LeafSDTools). Model: `ze0-h18-nor-flash.patch` using QEMU `pflash_cfi02` (or `cfi01`) if the command set fits, property `flash=FILE`; an erased image must boot like today. Never commit a real dump.
  - Input: `ze0-0010`, EXP-2026-11-08-M2.14-nor-eeprom, `docs/hardware/head-unit.md` (flash table), `tools/ce_drivers.py`.
  - Done when: boot with an erased 8 MiB file: `FlashManager` init returns success (log line or return value in the EXP), a write done by the guest is in the file after exit, and a second boot reads it back.
  - Stop: if the drivers use the RAM mirror only (`VSram` at `0x09a40000`) and never the chip while running, model the mirror load/store and say so.
  - Falsifier: the guest boots identically with and without the flash device and never accesses it.
  - Claims: C-7150–C-7159

- [x] **M8.H19 — Where does `Navi.exe` keep the last vehicle position, and who reads it at start**
  - Status: done · Owner: task/m8.h19-position-store · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: The quickest way to show a chosen place in the emulator is the way the car does it after a restart: the saved last position. `tools/datask_l3.py` already knows a position word and a default-position function per build. Find the persistent record (flash user area / `VSram`), its encoding and its reader.
  - Precheck: `grep -n 'default_position_fn\|"position"' tools/datask_l3.py` prints the EU2011 and US2011 entries.
  - Scope: static + L3, EU2011 then US2011: writers of the position word, the load at start (from `VSram`/flash record: offset, size, checksum), the default table used when the record is invalid. No QEMU run.
  - Input: `tools/datask_l3.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `tools/va_class.py`, `docs/research/rom-registry.md`.
  - Done when: `docs/firmware/position-store.md` gives record location, layout, checksum rule and the reader VA per build (`nk_decomp.py pdata` START for each `fn`), and `python3 tools/coord.py` converts a test coordinate to the stored form; EXP + claims.
  - Stop: if the load goes through a message from another process, name the sender and stop.
  - Falsifier: the start position ignores the record (changing the stored word in L3 does not change the first map request).
  - Claims: C-7160–C-7169
  - Result: EXP-2026-11-22-M8.H19-position-store; VSram block 0x8e is settings, not the position (pattern control negative); L3 falsifier not triggered: EU B48R058R vs B48R060R, US B38R0B0R vs B30R0E0R; coord selftest 24/24; position_store_l3 5/5 on both builds

- [ ] **M8.H20 — Start the emulator at a chosen place: seed the saved position**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.H18, M8.H19
  - Goal: Use the record of M8.H19 and the flash file of M8.H18 so `run.sh --start-position LAT,LON` boots with the map centred there — no GPS needed. First use: the four Poland tiles of the EU card.
  - Precheck: `docs/firmware/position-store.md` exists and `run.sh --help` lists the flash option.
  - Scope: `tools/ze0_seed.py position LAT,LON -o FLASH` writes the record (with `--selftest`), `run.sh --start-position` calls it.
  - Input: M8.H18 patch, `docs/firmware/position-store.md`, `tools/coord.py`.
  - Done when: two boots seeded with two positions request different tiles: `tools/ze0_sdtrace.py` (M8.H8) or the DMAC log shows the tile file of each position being read, and the tile names match `tools/mesh_grid.py` for those coordinates.
  - Stop: if the firmware rejects the record (checksum or a second copy), record the check and stop.
  - Falsifier: both boots read the same tile.
  - Claims: C-7170–C-7179

- [x] **M8.H21 — Is there a demo drive? Route simulation and other position sources inside `Navi.exe`**
  - Status: done · Owner: task/m8.h21-demo-drive · Critical: no · Pair: solo
  - Step: research
  - Depends: —
  - Goal: Many navigation programs can simulate driving a route. If this one can (a hidden or dealer menu), the emulator gets a moving position with no sensor model at all.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all Demo Simulat` prints candidates or nothing — both are results.
  - Scope: static, EU2011 and US2011: strings and menu resources for demo / simulation / dealer mode, the code that feeds positions in that mode, how it is switched on (registry value, key sequence, service menu of EXP-2026-11-05-M2.10-testmode).
  - Input: `tools/ce_strfind.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `tools/cehive.py`.
  - Done when: an EXP with the verdict (`present` with switch and VA, or `absent` with the searched vocabulary, encodings and module count) and, if present, a follow-up task added with `board.py add-task`.
  - Stop: one session.
  - Falsifier: a string hit has no code reference (dead resource).
  - Claims: C-7180–C-7189
  - Result: EXP-2026-11-22-M8.H21-demo-drive; verdict present; 149 EU / 151 US modules, switch + VAs; follow-up M8.H72

- [ ] **M8.H22 — Census of unmodelled hardware accesses in one boot: what to model next, by numbers**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1e (done)
  - Goal: Each missing device shows up as reads and writes to unmapped addresses. Rank them, so the next model is chosen by count and by who asks, not by guess.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem,unimp` writes a log (large: the README warns about polled registers).
  - Scope: new `tools/ze0_unmapped.py LOG`: group by 4 KiB block, count, first and last guest time, PC → module (via `tools/cerom.py`), and the name of the block from `docs/research/full-system-emulation.md`; streaming parser for multi-GB logs; `--selftest`.
  - Input: `tools/ce_qemu_probe.py`, `tools/ze0_regs.py`, `docs/research/full-system-emulation.md`.
  - Done when: `python3 tools/ze0_unmapped.py LOG --top 30` prints the ranked table for one EU2011 boot to idle; the EXP maps each of the top rows to an M8.H task or adds one line for it under `docs/research/qemu-connectors.md`; `--selftest` in `tools/selftest.py`.
  - Stop: one session.
  - Falsifier: the log is empty at idle (then every polled block is already stubbed and the table is the list of stubs).
  - Claims: C-7190–C-7199

- [ ] **M8.H23 — Guest profiler: where the CPU time goes (module and function histogram by PC sampling)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1e (done)
  - Goal: M8.C1e found a spinning driver thread by sampling the PC by hand about 20 times. Make it a tool: it tells why a boot is slow and which thread waits for which device.
  - Precheck: HMP `info registers` over the monitor socket prints `PC=` (the manual method of EXP-2026-11-22-M8.C1e-display-engine).
  - Scope: `tools/ze0_pcsample.py --monitor SOCK --n 500 --interval 0.05`: samples PC (and the current process if cheap), maps to module/function (`.pdata`), prints a histogram; `--selftest` with a fake monitor.
  - Input: `tools/qemu-ze0/run.sh` (monitor), `tools/cerom.py`, `tools/pdata.py`.
  - Done when: a histogram of an EU2011 run during the launcher wait and one at idle are in the EXP, each naming the top three functions; `--selftest` in `tools/selftest.py`.
  - Stop: one session.
  - Falsifier: samples are uniformly spread over one idle loop in both phases (then sampling by PC alone is useless and the EXP says what else is needed).
  - Claims: C-7200–C-7209

- [x] **M8.H24 — Emulator quick start for a human: build, boot a card, take a screenshot, in one page**
  - Status: done · Owner: task/m8.h24-emulator-quickstart · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: The knowledge to run `-M ze0` is spread over thirteen EXP records and a long README. Marek wants to start it and look. One page with the commands that work today and the known limits.
  - Precheck: `bash tools/qemu-ze0/build.sh --dry-run` and `bash tools/qemu-ze0/run.sh --help` run.
  - Scope: `docs/emulator/README.md`: prerequisites, build, fetch images, overlay, `ipl-patch`, run, screenshot, typical times, what works / what does not (table by device, linking `docs/research/qemu-connectors.md`), troubleshooting from the EXP records. Every command copied from a run on a clean checkout.
  - Input: `tools/qemu-ze0/README.md`, EXP-2026-11-21-M8.C1b … EXP-2026-11-22-M8.C1e, `docs/research/qemu-connectors.md`.
  - Done when: a second agent (the navigator, or a fresh shell with only the page) reaches a screenshot file by following the page; the EXP lists each command with its exit code.
  - Stop: one session.
  - Falsifier: a command on the page fails on a clean checkout.
  - Claims: C-7210–C-7219
  - Result: EXP-2026-11-22-M8.H24-emulator-quickstart; 7 claims C-7210–C-7216; every page command exit 0, 382721-pixel PNG at ~20 s

- [ ] **M8.H25 — Boot-time budget: from start to the idle UI, where the wall-clock minutes go**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1e (done)
  - Goal: Measure the phases (kernel, drivers, card mount, launcher waits, UI) in guest time and host time, with and without `-icount`, and list the three cheapest cuts.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) prints timestamps in the serial/DBGMSG logs.
  - Scope: measurement only: phase table from log markers (`tools/ze0_dbgmsg.py`), host seconds per guest second, the cost of each known wait (card mount, `ACM::WaitModule` timeouts). Options tried: `-icount` settings, the `-accel tcg` thread mode, `-d` flags off.
  - Input: `tools/ze0_dbgmsg.py`, `tools/qemu-ze0/run.sh`, EXP-2026-11-22-M8.C2a-serial-dma.
  - Done when: an EXP table phase → guest s → host s for two configurations, both from commands in the record, and a recommended default written into `run.sh --help` text or the README.
  - Stop: one session.
  - Falsifier: host time is dominated by one phase that no option changes (then the cut is a model, and the EXP names it).
  - Claims: C-7220–C-7229

- [x] **M8.H26 — `run.sh --card IMG`: derive `verinf`, `mapdb`, the overlay and the `ipl-patch` from the card**
  - Status: done · Owner: task/m8.h26-card-derive · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.C1d (done)
  - Goal: A run needs four hand-made inputs. All four are functions of the card image; a wrong `verinf` makes the launcher reject the card for a reason that has nothing to do with the test.
  - Precheck: `python3 tools/ze0_ipl.py patch --help` works; EXP-2026-11-22-M8.C1c-launcher-verinf names the header offsets the launcher reads.
  - Scope: `tools/ze0_card.py describe IMG` (map code, map-DB window, build name EU2011/US2011/other, FAT offset) with `--selftest`; `run.sh --card IMG` uses it and creates the overlay in the work directory. The card is never written.
  - Input: `tools/ze0_ipl.py`, `tools/qemu-ze0/mkoverlay.py`, `tools/hddinfo.py`, `tools/leafimg.py`.
  - Done when: `bash tools/qemu-ze0/run.sh --card EUCARD --machine ze0 …` with no `--verinf/--mapdb/--ipl-patch/--sd` reaches the same stage as the hand-built command; `python3 tools/ze0_card.py describe` prints different values for the EU and US heads; `--selftest` in `tools/selftest.py`.
  - Stop: one session.
  - Falsifier: the derived values differ from the ones used in EXP-2026-11-22-M8.C1c-launcher-verinf for the same card.
  - Claims: C-7230–C-7239
  - Result: EXP-2026-11-22-M8.H26-card-derive; describe EU QSD-302-100/16-16/EU2011/0x6400400 vs US QSD-301-100/US2011; full-card --card boot byte-identical serial.log to hand-built (1576 lines, applch_error 0, failsafe_start 0), card SHA unchanged; 16/16 synthetic selftest; claims_check/todo_check OK

- [x] **M8.H27 — `navdrv.dll`: what the GPS receiver says on `SCI7:` (frame format, rate, set-up commands)**
  - Status: done · Owner: task/m8.h27-navdrv-gps-protocol · Critical: yes · Pair: required
  - Step: reader
  - Depends: —
  - Goal: To inject a position we must speak the receiver's protocol. Read the driver: line settings, the set-up bytes it sends, the frame grammar it parses (NMEA sentences or a binary protocol), and which fields it extracts (time, latitude, longitude, height, speed, heading, satellites, fix quality).
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all SCI7:` names `navdrv.dll`; a search for `$GP` / `GGA` / `RMC` in the same module answers 'NMEA or not' in one command.
  - Scope: static, EU2011 (driver is in ROM A or B: say which; US2011 identity by `tools/fn_match.py`): open/IOCTL path, receive thread, parser state machine, checksum, units and scaling of each field, error handling when no data arrives. Also what it does at `0x19800000` and `0xffc5a000` (rows of `docs/hardware/head-unit.md`).
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `tools/nk_decomp.py`, `docs/hardware/head-unit.md`.
  - Done when: `docs/firmware/navdrv.md`: frame table (field, offset or token, unit, parser VA) complete enough to encode a fix; each `fn` is a `nk_decomp.py pdata` START; one hand-built example frame with its checksum computed by a snippet in the page; EXP + claims; `python3 tools/fn_audit.py` passes.
  - Stop: if the receiver protocol is a chip vendor's binary format with a public name, identify it by its sync bytes and cite the public spec instead of deriving every field.
  - Falsifier: the driver reads no serial data at all (position arrives pre-computed from another processor).
  - Claims: C-7240–C-7249
  - Result: EXP-2026-11-22-M8.H27-navdrv-gps-protocol; 7-bit sum + F0 frame, 4800 DCB, EU/US identical, fn_audit clean

- [x] **M8.H28 — `kepdrv.dll`: speed pulse, reverse signal and gyro — the dead-reckoning inputs**
  - Status: done · Owner: task/m8.h28-kepdrv · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: Between GPS fixes the unit dead-reckons from wheel pulses, a gyro and the reverse signal. A position that jumps without matching pulses may be filtered out, so the emulator needs these inputs too.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all KEPI` prints the driver's strings (`KEPI:TmuStcon…` in the M8.C table of `docs/research/todo-history-2026-11-05.md`).
  - Scope: static, EU2011: registers at `0xffc5a000`/`0xffc5b000` (pulse capture timer), where gyro samples come from (ADC, I²C, or the GPS module's frames), the reverse/illumination inputs (GPIO pins), sample rates, the structure handed to the positioning code.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `docs/hardware/head-unit.md`, `docs/research/full-system-emulation.md`.
  - Done when: `docs/firmware/kepdrv.md` with the register table, the sample structure and the units (pulses per metre source, gyro scale), each with a VA; EXP + claims; hardware-map rows updated.
  - Stop: one session; calibration constants learned at run time are named, not derived.
  - Falsifier: the driver has no timer-capture code (then pulses arrive over CAN: cross-check with M8.H49).
  - Claims: C-7250–C-7259
  - Result: EXP-2026-11-22-M8.H28-kepdrv; C-7250–C-7259; 10 claims, register/sample/unit doc + hardware row

- [ ] **M8.H29 — From driver to map: how a position fix travels inside `Navi.exe`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: Find the consumer side: which module receives `navdrv` data, the message or shared structure that carries a fix, the coordinate units at each hop, and where the fix becomes the map centre (`LOC_*` code; `LOC_map` is already known from M9.67).
  - Precheck: `python3 tools/callgraph.py --help` works and `grep -n 'LOC_map' docs/format/*.md docs/experiments/*M9.67* 2>/dev/null` finds the known entry.
  - Scope: static + L3, EU2011: callers of the driver's read/IOCTL, the fix structure, the conversion to the map coordinate (`tools/coord.py` units), the variable a debugger can read to learn 'where the unit thinks it is'.
  - Input: `tools/callgraph.py`, `tools/event_subs.py`, `tools/datask_l3.py`, `tools/coord.py`, `tools/sh4xref.py`.
  - Done when: an EXP with the chain (driver → structure → message → position word) and VAs, plus `tools/ze0_position.py read --monitor SOCK` that prints the current position from guest memory (selftest on a synthetic memory image; live use in M8.H31).
  - Stop: if more than one process is involved, document the first two hops and the final variable.
  - Falsifier: the position word of `tools/datask_l3.py` is never written after start (then it is a request parameter, not the vehicle position).
  - Claims: C-7260–C-7269

- [x] **M8.H30 — `tools/ze0_peers/gps.py`: a GPS receiver peer (fixed fix, NMEA/GPX replay)**
  - Status: done · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H27
  - Goal: The receiver model as a host program on the `sci7` chardev: sends frames in the format of `docs/firmware/navdrv.md` at the real rate, answers the driver's set-up commands.
  - Precheck: `docs/firmware/navdrv.md` has the frame table and the example frame.
  - Scope: encoder for every field of the table, `--fix LAT,LON[,ALT]`, `--speed`, `--heading`, `--time`, `--no-fix`, `replay FILE.gpx|.nmea --rate X`; a control socket so `tools/ze0_ui.py` can change the fix; `--selftest` encodes the example frame of the doc byte for byte and round-trips random fixes. No QEMU needed for done.
  - Input: `docs/firmware/navdrv.md`, `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_peers/gps.py --selftest` passes and is in `tools/selftest.py`; the example frame of the doc is reproduced; a GPX track of three points yields frames with interpolated positions (checked in the selftest).
  - Stop: one session.
  - Falsifier: the selftest passes with a wrong checksum routine (no negative control).
  - Claims: C-7270–C-7279
  - Result: EXP-2026-11-22-M8.H30-gps-peer; 27 selftests, doc frame byte-exact, GPX 5 samples; gate parts PASS except pre-existing C-6728 count

- [ ] **M8.H31 — A GPS fix reaches the map: inject a position on `-M ze0` and read it back from the guest**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: model
  - Depends: M8.H1, M8.H30, M8.H29
  - Goal: The first end-to-end sensor test: the peer sends a fix, the firmware accepts it, the position variable follows.
  - Precheck: the loop-back of M8.H1 passes on `sci7` and `python3 tools/ze0_peers/gps.py --selftest` passes.
  - Scope: EU2011 on the EU card; two fixes far apart (two different tiles of the card). Evidence from guest memory (`tools/ze0_position.py`) and from the SD trace; a screenshot only if M8.C1f is merged.
  - Input: `tools/ze0_peers/gps.py`, `tools/ze0_position.py`, `tools/ze0_sdtrace.py` if merged, `docs/research/qemu-connectors.md`.
  - Done when: for each injected fix, `ze0_position.py read` returns that position within the documented resolution, and the tile containing it is read from the card; with the peer silent (`--no-fix`) the position stays at the start value — the negative control. EXP + claims.
  - Stop: if the firmware ignores fixes without dead-reckoning inputs, record the filter condition (VA) and hand over to M8.H32.
  - Falsifier: the position follows the fix even when the frame checksum is wrong (then the parser path taken is not the one documented).
  - Claims: C-7280–C-7289

- [ ] **M8.H32 — Wheel pulses, gyro and reverse on `-M ze0`, driven from the same track as the GPS**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.H28
  - Goal: Model the dead-reckoning inputs of `docs/firmware/kepdrv.md` so speed and turn rate agree with the injected GPS track.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` shows accesses at `0xffc5a000`/`0xffc5b000` (unmodelled today).
  - Scope: patch `ze0-h32-dr-sensors.patch`: pulse-capture timer block with a pulse rate set over QMP/qom (`speed-kmh`), gyro samples through the path M8.H28 found, reverse and illumination pins; `tools/ze0_peers/gps.py` drives them from the track.
  - Input: `docs/firmware/kepdrv.md`, `ze0-0003`, `tools/ze0_peers/gps.py`.
  - Done when: with a constant 50 km/h the firmware's speed variable (VA from M8.H28) settles within 5 % of it, and at 0 km/h it reads zero; EXP + claims.
  - Stop: if the scale depends on a learned calibration, seed the calibration value and say so.
  - Falsifier: the speed variable does not change with the pulse rate.
  - Claims: C-7290–C-7299

- [ ] **M8.H33 — Drive a track: GPX replay with screenshots every few seconds**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H31, M8.C1f
  - Goal: The demonstration Marek asked for: the emulator follows a recorded drive and the map scrolls.
  - Precheck: M8.H31 passes and `tools/ze0_screenshot.py grab` shows the map.
  - Scope: a scenario file for `tools/ze0_ui.py` (or a shell loop if M8.H7 is not merged): replay a 2 km track on a tile of the EU card, one screenshot per 5 s of guest time. Screenshots stay in `archive/` (vendor graphics — never committed); the record holds hashes and a description.
  - Input: `tools/ze0_peers/gps.py`, `tools/ze0_ui.py`, `tools/ze0_screenshot.py`.
  - Done when: the screenshot sequence shows at least three distinct frames, and the position read from the guest at each frame equals the track point within the documented resolution; the EXP lists frame hash and position per step.
  - Stop: if the map does not redraw without speed pulses, depend on M8.H32 and stop.
  - Falsifier: all frames are identical while the guest position changes.
  - Claims: C-7300–C-7309

- [ ] **M8.H34 — Map matching at L4: does the cursor snap to a road, and which tile section does that use**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: research
  - Depends: M8.H33
  - Goal: Drive once along a road of a factory tile and once 150 m beside it. If the displayed position snaps to the road, map matching works in the emulator, and the SD trace tells which section of the tile it read — the first L4 evidence about section 2 that needs no route calculation.
  - Precheck: M8.H33 passes on a tile whose roads `tools/tilewriter.py` or `tools/parcel_census.py` can list.
  - Scope: two tracks built from the decoded geometry of one road (offset 0 m and 150 m), same speed; compare matched position (guest variable from M8.H29) against the injected one; SD/tile read ranges per run.
  - Input: `tools/ze0_peers/gps.py`, `tools/ze0_position.py`, `tools/ze0_sdtrace.py`, `tools/parcel_census.py`.
  - Done when: an EXP table track → injected vs matched distance per sample, and the tile sections read; verdict `snaps` / `does not snap` / `not observable`, with the guest variable that holds the matched position named.
  - Stop: one session after M8.H33.
  - Falsifier: the matched position equals the injected one in both runs (no matching visible) — then name what input is missing.
  - Claims: C-7310–C-7319

- [ ] **M8.H35 — `lcddrv.dll`: the serial protocol with the display unit on `SCI3:`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: The display unit is a separate assembly driven over `SCI3:` besides the video signal. Read what goes over that line: brightness, power, status, and whether touch coordinates or key presses come back on it.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all SCI3:` names `lcddrv.dll`.
  - Scope: static, EU2011: line settings, frame grammar both directions, command list with meaning, the start-up handshake the driver waits for (and its timeout), events delivered upward.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `docs/hardware/head-unit.md`.
  - Done when: `docs/firmware/lcddrv.md` with the frame grammar and command table (VA per row), the handshake and the answer that satisfies it; EXP + claims; hardware-map row `SCI3:` updated.
  - Stop: one session.
  - Falsifier: the driver only writes and never reads the line (then input comes from elsewhere: M8.H36).
  - Claims: C-7320–C-7329

- [x] **M8.H36 — Where touch comes from: from the panel to the UI message (path, coordinates, calibration)**
  - Status: done · Owner: task/m8.h36-touch-path · Critical: yes · Pair: required
  - Step: reader
  - Depends: —
  - Goal: Marek wants touch input in the emulator. Find the source of touch samples (display unit frames on `SCI3:`, an ADC behind `kepdrv`, a CE touch driver, or the audio microcontroller), the coordinate range and calibration, and the message that reaches the UI (`auiapp`).
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all Touch` and the registry search `python3 tools/cehive.py … | grep -i touch` (hives of EXP-2026-11-20-M8.E2-registry-loaded) return candidates.
  - Scope: static, EU2011: driver, sample format, press/release/drag semantics, calibration data and where it is stored, the UI-side entry point (window message or queue) with VA. State which of the candidates of row C20 in the M8.C table is true.
  - Input: `tools/cehive.py`, `tools/ce_drivers.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `tools/event_subs.py`.
  - Done when: `docs/firmware/touch.md`: the path as a chain with VAs, the wire or register format of one sample, the screen coordinate mapping (800 × 480), and the cheapest injection point for an emulator (device level, and message level as a fallback); EXP + claims.
  - Stop: two sessions; if two paths exist (touch and a remote), document touch only.
  - Falsifier: no code path delivers coordinates to the UI process (then the unit has no touch and the EXP says what the 2011 unit uses).
  - Claims: C-7330–C-7339
  - Result: EXP-2026-11-22-M8.H36-touch-path; C-7330–C-7339; touch.md §1–7

- [x] **M8.H37 — Hard keys and the rotary knob: source, key codes, and the table of names**
  - Status: done · Owner: task/m8.h37-keys · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: The unit has hard keys (map, menu, destination, zoom, day/night, audio keys, steering-wheel keys). Find where each arrives (display unit, audio microcontroller on `SCI1:`, GPIO matrix) and build the key-code table the injection tool needs.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all KEY_ Key` prints candidates; `tools/event_subs.py --help` works.
  - Scope: static, EU2011: per source the frame or scan format, the code → function table, long-press/repeat rules, how the code reaches the UI. Names from firmware strings where they exist, otherwise from the owner's manual wording.
  - Input: `tools/event_subs.py`, `tools/sh4xref.py`, `tools/callgraph.py`, `docs/firmware/vehicle.md`.
  - Done when: `docs/firmware/keys.md` with one row per key (name, source, raw code, VA of the table or switch); EXP + claims.
  - Stop: one session per source; stop after the two sources that carry the navigation keys.
  - Falsifier: the same raw code maps to two functions depending on a mode the table does not show.
  - Claims: C-7340–C-7349
  - Result: EXP-2026-11-22-M8.H37-keys; 4 sources, 15 tables/174 pairs decoded, C-7340-C-7349; falsifier negative

- [x] **M8.H38 — `tools/ze0_peers/panel.py`: touch and key injection peer (`tap`, `drag`, `key`)**
  - Status: done · Owner: task/m8.h38-panel-peer · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H36, M8.H37
  - Goal: The display-unit/input model as a host program: answers the start-up handshake of `docs/firmware/lcddrv.md` and sends touch and key events in the format of `docs/firmware/touch.md` and `keys.md`.
  - Precheck: the three documents exist and each names an injection point.
  - Scope: commands `tap X Y [--ms N]`, `drag X1 Y1 X2 Y2`, `key NAME [--long]`, control socket for `tools/ze0_ui.py`; if touch is not on a serial line, the same commands drive the device or message path M8.H36 chose (through QMP/gdb), behind the same interface. `--selftest` against the documented example frames.
  - Input: `docs/firmware/touch.md`, `docs/firmware/keys.md`, `docs/firmware/lcddrv.md`, `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_peers/panel.py --selftest` passes and is in `tools/selftest.py`, with a negative control (out-of-range coordinate refused).
  - Stop: one session.
  - Falsifier: the encoder output differs from the example frame in the document.
  - Claims: C-7350–C-7359
  - Result: EXP-2026-11-22-M8.H38-panel-peer; 32/32 selftest checks; tool:ze0_peers.panel PASS

- [ ] **M8.H39 — A tap changes the screen: touch injection on `-M ze0`, end to end**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: model
  - Depends: M8.H1, M8.H38, M8.C1f
  - Goal: First interactive L4 test: tap a visible button and see the UI react.
  - Precheck: `tools/ze0_screenshot.py grab` shows the idle screen and `python3 tools/ze0_peers/panel.py --selftest` passes.
  - Scope: EU2011: one tap on a button of the idle screen (coordinates from a screenshot), one hard key; screenshots before and after; repeat once to show the result is stable.
  - Input: `tools/ze0_peers/panel.py`, `tools/ze0_screenshot.py`, `tools/ze0_ui.py` if merged.
  - Done when: the after-tap screenshot differs from the idle one and equals the after-tap screenshot of the second run (hashes in the EXP); a tap on an empty area leaves the screen unchanged — the negative control; the UI message of `docs/firmware/touch.md` is seen at its VA (breakpoint hit count).
  - Stop: if the event arrives (breakpoint hit) but the UI does not react, record the UI state and stop.
  - Falsifier: the screen changes without any tap between the two screenshots (animation), making the comparison meaningless — then compare a named region.
  - Claims: C-7360–C-7369

- [ ] **M8.H40 — Live window: host mouse and keyboard drive the emulated unit**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H4, M8.H38
  - Goal: For exploring the UI by hand: `run.sh --display gtk` (or VNC) where a mouse click is a tap and mapped keyboard keys are the hard keys.
  - Precheck: `run.sh --display` shows the guest screen (M8.H4) and the panel peer selftest passes.
  - Scope: a bridge from QEMU input events to the panel peer: either QMP input events read by a host script, or a small input handler in `ze0-gfx` that forwards to the peer socket; key map file.
  - Input: M8.H4 patch, `tools/ze0_peers/panel.py`.
  - Done when: a recorded session (QMP `input-send-event` script, so it is reproducible without a human) taps the same button as M8.H39 through the display path and gets the same after-tap hash.
  - Stop: one session.
  - Falsifier: the click lands at a different guest coordinate than requested (scaling error) — measured by the peer's log.
  - Claims: C-7370–C-7379

- [ ] **M8.H41 — Scenario: set a destination and calculate a route at L4**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.H39, M8.H7
  - Goal: The first routing test in the full system: enter a destination by the map or by a stored point, start route calculation, capture the result. It tells which files the router opens (section 2, `LEV3456R`) on a factory card and later on ours.
  - Precheck: M8.H39 passes; `python3 tools/ze0_ui.py --selftest` passes.
  - Scope: a scenario file of taps for EU2011 on the EU card (two points inside one tile, then two tiles apart); screenshots and the SD trace per phase. No generated card yet.
  - Input: `tools/ze0_ui.py`, `tools/ze0_peers/panel.py`, `tools/ze0_sdtrace.py`, `docs/format/map-tiles.md`.
  - Done when: the scenario runs unattended twice with equal final hashes, and the EXP lists the files and byte ranges read between 'calculate' and 'route shown'; or the screen where it stops is described with its log.
  - Stop: two sessions; stop at the first screen that needs an input no peer provides and name it.
  - Falsifier: no file is read during calculation (then the graph was preloaded and the trace window must start earlier).
  - Claims: C-7380–C-7389

- [ ] **M8.H42 — Screen catalogue: walk the menu tree by script and record every screen reached**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H39, M8.H7
  - Goal: A map of the UI (screen → how to reach it → what it needs) makes later scenarios short and shows which features work in the emulator.
  - Precheck: M8.H39 passes.
  - Scope: breadth-first walk from the idle screen to depth 2 by tapping the buttons found on each screenshot (button positions listed by hand for the first screens); for each screen: path, hash, short description, devices it asked for (from logs). Screenshots stay in `archive/`.
  - Input: `tools/ze0_ui.py`, `tools/ze0_screenshot.py`.
  - Done when: `docs/emulator/screens.md` lists at least fifteen screens with path and hash, reproducible by `python3 tools/ze0_ui.py run docs/emulator/scenarios/walk.txt` (exit 0 twice).
  - Stop: stop at depth 2 or thirty screens.
  - Falsifier: two runs of the walk give different hashes for the same path.
  - Claims: C-7390–C-7399

- [ ] **M8.H43 — `anwdrv.dll`: the frame protocol with the audio microcontroller on `SCI1:` and the start-up handshake**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: reader
  - Depends: —
  - Goal: The emulator's launcher waits out about 27 module timeouts of 30 s because nobody answers on `SCI1:` (project notes 2026-11-22, EXP-2026-11-22-M8.C2a-serial-dma). The driver multiplexes several logical devices (`AUD`, `TNR`, `TMC`, `ANT`, `UPD`, `PDT`) over one framed link. Read the frame grammar and the exchange that reports a module as present.
  - Precheck: EXP-2026-11-22-M8.C2a-serial-dma quotes the first frame the guest sends; `python3 tools/ce_strfind.py archive/head256.img --encoding all WaitModule` finds the waiting code.
  - Scope: static, EU2011: framing (start/end marks, escaping, checksum), addressing of logical devices, the request/response pairs used during launch, timeouts and retries, and what `ACM::WaitModule` needs to return success. Message catalogue for the launch phase only.
  - Input: EXP-2026-11-22-M8.C2a-serial-dma, `tools/acm_id_scan.py`, `tools/applaunch_table.py`, `tools/sh4dis.py`, `tools/sh4xref.py`.
  - Done when: `docs/firmware/anwdrv.md`: frame grammar with the checksum rule verified on the logged frame (a snippet recomputes its last byte), the launch-phase message table with VAs, and the minimal reply set; EXP + claims.
  - Stop: two sessions; radio, CD and amplifier messages are out of scope.
  - Falsifier: the checksum rule fails on a second logged frame.
  - Claims: C-7400–C-7409

- [ ] **M8.H44 — `tools/ze0_peers/micon.py`: audio-microcontroller peer that answers the launch handshake**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H43
  - Goal: A host program on the `sci1` chardev that replies as `docs/firmware/anwdrv.md` requires, so the launcher stops waiting.
  - Precheck: `docs/firmware/anwdrv.md` has the reply set.
  - Scope: frame codec, a table-driven responder (request pattern → reply), logging of unknown requests, control socket for later key events; `--selftest` replays the logged guest frames and checks the replies' framing and checksum.
  - Input: `docs/firmware/anwdrv.md`, EXP-2026-11-22-M8.C2a-serial-dma, `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_peers/micon.py --selftest` passes and is in `tools/selftest.py`, with a corrupted-checksum frame rejected.
  - Stop: one session.
  - Falsifier: the selftest accepts a frame with a wrong checksum.
  - Claims: C-7410–C-7419

- [ ] **M8.H45 — Boot without the 30-second waits: the micon peer on `-M ze0`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.H1, M8.H44
  - Goal: Measure the launch with the peer attached: the module waits should succeed at once.
  - Precheck: M8.H1's loop-back passes on `sci1` and the peer selftest passes.
  - Scope: EU2011, one boot with and one without the peer, same options; count `WaitModule` timeouts and time to `Finish Launch Threads` in guest seconds.
  - Input: `tools/ze0_peers/micon.py`, `tools/ze0_dbgmsg.py`.
  - Done when: the EXP quotes both counts and both times from `tools/ze0_dbgmsg.py` output; the timeout count with the peer is 0, or each remaining timeout is listed with the request the peer could not answer; `run.sh --peers micon` starts it by default if it helps.
  - Stop: if a module needs more than a presence reply (firmware version exchange, update check), answer the first level and list the rest.
  - Falsifier: the timeout count is the same with and without the peer.
  - Claims: C-7420–C-7429

- [ ] **M8.H46 — Sound out of the emulator: SSI audio output to a WAV file**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.C1b (done)
  - Goal: The SoC plays two PCM streams over SSI (`wavessi1.dll`, `wavessi2.dll`; DMA channels in `docs/hardware/head-unit.md`). Capturing them makes guidance prompts and beeps testable.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` shows accesses at the SSI block `0xffe00000` (unmodelled).
  - Scope: static read of the two wave drivers (sample format, rate, DMA use), then patch `ze0-h46-ssi-audio.patch`: SSI transmit as a DMA sink on the HPB-DMAC model, samples to a QEMU audio backend (`-audiodev wav`); record path: silence.
  - Input: `ze0-0009`, `docs/hardware/head-unit.md`, `tools/sh4dis.py`.
  - Done when: the wave driver's init succeeds, and when the guest plays any sound (the start-up beep, or a `waveOut` call forced through gdb) the WAV file holds non-silent samples at the driver's sample rate; with no playback the file is silent.
  - Stop: if playback goes through the external DSP path only (`DspDrv`), record the hand-off and stop.
  - Falsifier: the driver reports success but never starts a DMA transfer.
  - Claims: C-7430–C-7439

- [ ] **M8.H47 — `Speech.exe` does not start on `-M ze0`: who provides `AppTimerDll`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1d (done)
  - Goal: After ROM A was joined, `Speech.exe` fails because `AppTimerDll` exists only in ROM image C (project notes 2026-11-22). Find how the real unit resolves it (a module of the kernel half that lives in the unit's flash, another name, load order) and get the voice process running.
  - Precheck: `python3 tools/cerom.py --image-start 0x5200200 archive/head256.img modules | grep -i apptimer` finds it in C and the same for `0x200200`/`0x3e00200` finds nothing.
  - Scope: static: import table of `Speech.exe`, the modules list of A/B/C, the launcher's table (`tools/applaunch_table.py`); then the smallest loader/`ipl-patch` change that makes the import resolve. EU2011.
  - Input: `tools/applaunch_table.py`, `tools/ze0_ipl.py`, `tools/cerom.py`, EXP-2026-11-22-M8.C1d-multi-xip.
  - Done when: `Speech.exe` is running at idle (process list via the kernel structures, or its DBGMSG lines) on one boot; or the EXP shows that the unit's flash supplies the module and names it as a dependency on the dump of M6.18.
  - Stop: one session.
  - Falsifier: `Speech.exe` imports nothing from `AppTimerDll` (the failure has another cause).
  - Claims: C-7440–C-7449

- [ ] **M8.H48 — Hear a guidance prompt: capture one spoken instruction at L4 and name its source file**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: research
  - Depends: M8.H46, M8.H47
  - Goal: With sound out and the voice process running, trigger one prompt and record it. Together with the SD trace it shows which `SPEECH/` file and offset a phrase comes from — input for the Polish voice question (M4.57) and the sound inventory (M4.60).
  - Precheck: M8.H46's WAV capture works and `Speech.exe` runs.
  - Scope: trigger by the cheapest path (a volume-setting test tone, a guidance repeat key, or a direct call found in M4.60); WAV stays in `archive/`.
  - Input: `tools/ze0_sdtrace.py`, M4.60's inventory if merged, `docs/format/assets.md`.
  - Done when: a WAV with speech-band energy (duration and RMS quoted from a command) and the `SPEECH/` read ranges that preceded it; EXP + claims.
  - Stop: if no prompt can be triggered without a route, depend on M8.H41 and stop.
  - Falsifier: audio appears with no read from `SPEECH/` (TTS from ROM data).
  - Claims: C-7450–C-7459

- [ ] **M8.H49 — `CAN.dll`: the UART protocol with the VCAN microcontroller and the list of vehicle signals**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: The SH-4 gets vehicle data as frames over `UAT3:`. List the frame grammar and every signal the applications read: speed, reverse, ignition/ACC, illumination, parking brake, and the EV data the Leaf screens show (state of charge, range, charging state).
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all VCAN_` prints signal-name strings (the M8.C table names `VCAN_R_VDC`).
  - Scope: static, EU2011: framing and checksum, request/periodic model, signal table (name, frame id, bytes, scale) from the decode functions, which process consumes each (`DriveComputer`, `Navi.exe`, `PowerMonitor`). Cross-reference `docs/firmware/vehicle.md`.
  - Input: `docs/firmware/vehicle.md`, `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/callgraph.py`.
  - Done when: `docs/firmware/can.md` with the frame grammar and at least the signals speed, reverse, ignition, illumination and state of charge (VA per row); EXP + claims.
  - Stop: two sessions; the full signal list may stay partial if the five named signals are done.
  - Falsifier: signal names exist as strings but no decode function references them.
  - Claims: C-7460–C-7469

- [ ] **M8.H50 — `tools/ze0_peers/vcan.py`: vehicle peer (ignition, speed, reverse, lights, state of charge)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H49
  - Goal: The VCAN microcontroller as a host program on the `uat3` chardev, sending the periodic frames of `docs/firmware/can.md` from a small vehicle state.
  - Precheck: `docs/firmware/can.md` has the frame grammar and the five signals.
  - Scope: state model with setters (`ignition on|off`, `speed KMH`, `reverse on|off`, `lights on|off`, `soc PERCENT`), periodic sender, control socket; `--selftest` on the documented example frames.
  - Input: `docs/firmware/can.md`, `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_peers/vcan.py --selftest` passes and is in `tools/selftest.py`, with a negative control.
  - Stop: one session.
  - Falsifier: the encoder disagrees with the documented example frame.
  - Claims: C-7470–C-7479

- [ ] **M8.H51 — Lights on, night map: ignition and illumination from the vehicle peer change the screen**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.H3, M8.H50, M8.C1f
  - Goal: First vehicle-signal test at L4: the map palette should switch to night colours when the illumination signal is on.
  - Precheck: M8.H3's loop-back passes on `uat3` and the peer selftest passes.
  - Scope: EU2011; screenshots with lights off and on; the consumer variable read through gdb as second evidence.
  - Input: `tools/ze0_peers/vcan.py`, `tools/ze0_screenshot.py`.
  - Done when: the two screenshots differ in palette (hashes and a mean-brightness number from a command in the EXP), and switching back restores the first hash.
  - Stop: if day/night is decided by the display unit or a clock, record the source and stop.
  - Falsifier: the screen is identical in both states.
  - Claims: C-7480–C-7489

- [ ] **M8.H52 — EV screens at L4: state of charge and range from the vehicle peer (reachable-area map)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: research
  - Depends: M8.H51
  - Goal: The Leaf unit draws a reachable area on the map and lists charging stations (`REFER002`, the EV layer). With an injected state of charge these screens become testable — the place where EV data of a generated card would show.
  - Precheck: M8.H51 passes.
  - Scope: set two states of charge; reach the EV information screen by script; SD trace for `REFER002` reads.
  - Input: `tools/ze0_peers/vcan.py`, `tools/ze0_ui.py`, `tools/ze0_sdtrace.py`, `docs/format/refer.md`.
  - Done when: screenshots for the two values differ in the range display, and the EXP lists which `REFER002` files were read; or the missing input is named.
  - Stop: one session.
  - Falsifier: the range display ignores the injected value.
  - Claims: C-7490–C-7499

- [ ] **M8.H53 — `PowerMonitor`: the power state machine (ACC on/off, start handshake, shutdown and what it saves)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: Row C4 of the peripheral table (vehicle microcontroller / power state) was never read. Find what the unit expects at start (a 'system ready' exchange), and what happens at ACC off: which data is flushed to flash, in what order, with what timeout.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all PowerMonitor ActivateCtlDriver` prints both names.
  - Scope: static, EU2011: states and transitions, the inputs that move them (CAN signal, GPIO, micon frame), the save path (modules notified, flash regions written), timeouts.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/event_subs.py`, `tools/applaunch_table.py`, `docs/hardware/head-unit.md`.
  - Done when: `docs/firmware/power.md` with the state diagram as a table (state, input, next state, VA) and the shutdown save list; EXP + claims.
  - Stop: two sessions.
  - Falsifier: no code path leads from an ACC-off input to a flash write.
  - Claims: C-7500–C-7509

- [ ] **M8.H54 — Clean shutdown at L4: ACC off, data saved to the flash file, restored at the next boot**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.H18, M8.H53, M8.H50
  - Goal: Close the persistence loop: after an ACC-off from the vehicle peer the flash file changes, and the next boot starts from the saved state.
  - Precheck: the flash file of M8.H18 persists guest writes and `docs/firmware/power.md` names the ACC input.
  - Scope: one run: boot, change a setting or position, ACC off, wait for the save, stop; second run: read back.
  - Input: M8.H18 patch, `tools/ze0_peers/vcan.py`, `docs/firmware/power.md`.
  - Done when: the flash file differs before/after shutdown in the region `docs/firmware/power.md` predicts (offsets from `cmp -l | head`), and the second boot shows the saved value.
  - Stop: one session.
  - Falsifier: the flash file is unchanged after a completed shutdown sequence.
  - Claims: C-7510–C-7519

- [ ] **M8.H55 — Bluetooth module on `SCI8:`: wire protocol and what makes its start-up finish**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: `BT_FW.dll` and `BT_MGR.dll` talk to a Bluetooth module over the high-speed UART. For the emulator we need the transport (HCI H4, BCSP, or a vendor command set), whether firmware is downloaded into the module at start, and the shortest exchange that lets the stack settle (present, or cleanly absent). M1.41 maps the stack above; this task is the wire only.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all SCI8:` names both modules.
  - Scope: static, EU2011: line settings, packet framing, first ten exchanges after open, timeout behaviour with a silent line, module vendor strings.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, M1.41's EXP if merged, `docs/hardware/head-unit.md`.
  - Done when: `docs/firmware/bt-wire.md`: transport verdict with evidence (packet indicator bytes or the vendor framing), the start-up exchange table, and the recommended stub (`absent` or `minimal present`); EXP + claims.
  - Stop: one session.
  - Falsifier: the modules never write to the line during start (BT is started on demand only).
  - Claims: C-7520–C-7529

- [ ] **M8.H56 — Bluetooth stub peer: the stack settles quickly, with the module absent or minimally present**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: M8.H1, M8.H55
  - Goal: Implement the stub chosen in `docs/firmware/bt-wire.md` as `tools/ze0_peers/bt.py` on the `sci8` chardev and measure the effect on boot.
  - Precheck: `docs/firmware/bt-wire.md` names the stub; M8.H1's loop-back works.
  - Scope: table-driven responder with `--selftest`; one boot with and without.
  - Input: `docs/firmware/bt-wire.md`, `docs/research/qemu-connectors.md`.
  - Done when: `python3 tools/ze0_peers/bt.py --selftest` passes (in `tools/selftest.py`); the EXP quotes the Bluetooth-related timeout count and guest time with and without the peer from log commands.
  - Stop: one session.
  - Falsifier: no difference in the Bluetooth log lines with the peer attached.
  - Claims: C-7530–C-7539

- [ ] **M8.H57 — USB host on `-M ze0`: the OHCI controller at `0xffe70400`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: model
  - Depends: M8.B5 (done)
  - Goal: The unit has a USB 1.1 host (`UsbOhci.dll`; the kernel resets the block at `0xffe70000` and waits on `+0x808`). QEMU has a sysbus OHCI model; wire it in with the small wrapper block so USB devices can be attached.
  - Precheck: `grep -n 'ffe70' tools/qemu-ze0/patches/*.patch` shows today's stub; the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) logs the `UsbOhci` init result.
  - Scope: patch `ze0-h57-usb-ohci.patch`: `sysbus-ohci` at `0xffe70400`, the interrupt of the hardware map, the wrapper registers the kernel touches (reset/clock bits at `+0x808`), a USB bus; no device attached by default.
  - Input: `docs/hardware/head-unit.md` (USB row), `tools/sh4dis.py` on `UsbOhci.dll`, QEMU `hw/usb/hcd-ohci-sysbus.c`.
  - Done when: `UsbOhci.dll` init returns success and the root hub is enumerated (guest reads port status; log or breakpoint evidence); boot without devices otherwise unchanged.
  - Stop: if the driver expects a non-standard register layout, list the differences and stop.
  - Falsifier: the driver never touches the OHCI registers after the wrapper reset.
  - Claims: C-7540–C-7549

- [ ] **M8.H58 — A USB stick in the emulator: `usb-storage` appears as the unit's USB disk**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.H57
  - Goal: Attach a FAT image as USB mass storage and see the firmware mount it — the path for music files and a candidate path for user-side data exchange.
  - Precheck: M8.H57 passes.
  - Scope: `run.sh --usb-disk FILE`; small FAT16/FAT32 image with one text file.
  - Input: M8.H57 patch.
  - Done when: the guest reads sectors of the image (QEMU block trace) and a mount line or directory read is logged.
  - Stop: if the class driver needs an interrupt-transfer feature the model lacks, record it and stop.
  - Falsifier: the device enumerates but no sector is read.
  - Claims: C-7550–C-7559

- [ ] **M8.H59 — I²C on `-M ze0`: a logging bus model that tells which slaves the firmware addresses**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.B5 (done)
  - Goal: M1.40 could not recover the I²C slave addresses statically (`docs/hardware/head-unit.md`, 'I2C map (static)': address unknown in every row). The emulator can list them at run time: model the controller at `0xffc71000` far enough that transfers start, answer NACK, and log address, direction and the calling module.
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` shows accesses at `0xffc71000`.
  - Scope: patch `ze0-h59-i2c-log.patch`: controller registers as `I2C.dll` uses them (read the driver first), every address NACKed, a trace line per transfer; `tools/ze0_regs.py` summary.
  - Input: `tools/sh4dis.py` on `I2C.dll`, `ze0-0003`, EXP-2026-11-22-M1.40-hw-map-ii.
  - Done when: one boot lists the slave addresses probed with counts and caller module, in an EXP table, and the 'I2C map (static)' table of `docs/hardware/head-unit.md` gains the addresses with status OBSERVED (run time).
  - Stop: one session.
  - Falsifier: no transfer is started during a boot to idle.
  - Claims: C-7560–C-7569

- [ ] **M8.H60 — GPIO on `-M ze0`: logging model of the on-chip ports and the external latch**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.B5 (done)
  - Goal: Pin roles are a 'static limit' in `docs/hardware/head-unit.md` (M1.40: masks and directions are configured at run time). A model that stores writes and logs every access with the calling module gives the run-time half of the pin map, and a place to drive inputs (reverse, illumination, card detect, mute).
  - Precheck: the boot recipe of EXP-2026-11-22-M8.C1e-display-engine (`tools/qemu-ze0/run.sh --machine ze0 --image archive/head256.img --sd CARD --ipl-patch FILE`, EU2011) with `-d invalid_mem` shows accesses at `0xffc41000`–`0xffc43000` or `0x19400000`.
  - Scope: patch `ze0-h60-gpio-log.patch`: registers as plain latches, input values settable as qom properties, trace line per access; `tools/ze0_regs.py` report by pin.
  - Input: `tools/sh4dis.py` on `GPIO.dll`, `tools/ze0_regs.py`, `docs/research/full-system-emulation.md`.
  - Done when: an EXP table pin (port, bit) → direction → writers/readers by module → guessed role, for one boot to idle; `docs/hardware/head-unit.md` GPIO row links it.
  - Stop: one session.
  - Falsifier: the applications reach GPIO only through a driver that never touches the registers in a boot.
  - Claims: C-7570–C-7579

- [ ] **M8.H61 — Reversing camera path: a test picture on the video input when reverse is on**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Priority: low (after touch, GPS and the vehicle peer)
  - Depends: M8.H49, M8.C1f
  - Goal: Low priority. `VIN.dll` brings the camera image through the SoC. A static test image on reverse proves the path and exercises the reverse signal.
  - Precheck: `docs/firmware/camera.md` exists and names the driver entry points.
  - Scope: static read of the capture path first (which block, how the image reaches the display planes); model only if it is a plane switch plus a frame buffer.
  - Input: `docs/firmware/camera.md`, `ze0-0013`, `tools/ze0_peers/vcan.py`.
  - Done when: an EXP with the verdict (`simple plane switch` + patch showing a test image on reverse, or `needs a video-capture model` with the register list) .
  - Stop: one session; do not model a video decoder.
  - Falsifier: reverse changes nothing on the display path.
  - Claims: C-7580–C-7589

- [ ] **M8.H62 — `fmmdrv.dll` and the TMC path: where a traffic message enters, and what it looks up on the card**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: reader
  - Depends: —
  - Goal: `RDSTM001.DAT` and `LCTBL001.DAT` must be generated for Poland, and their only consumer is traffic: a TMC event carries a location code that is looked up in them. Find the entry point of a decoded TMC message (after `fmmdrv` at `0xffc55000` and the tuner path through `anwdrv`), so an event can be injected without modelling a radio.
  - Precheck: `python3 tools/tmc_req_l3.py --help` and `python3 tools/lctbl_lookup_l3.py --help` work (the L3 side exists); `python3 tools/ce_strfind.py archive/head256.img --encoding all fmmdrv` names the driver.
  - Scope: static, EU2011: the path from the driver to the traffic module, the structure of one decoded message (country, table, location, event, direction, extent), the function that receives it (VA), and the card reads it causes. Relation to M4.51/M4.62 (the `0x14f4` messages) stated.
  - Input: `tools/tmc_req_l3.py`, `tools/lctbl_lookup_l3.py`, `tools/tmc_reception.py`, `docs/format/rdstm.md`, EXPs of M4.51 and M4.49.
  - Done when: `docs/firmware/tmc-path.md` with the chain and the injection point (function VA + argument layout, `nk_decomp.py pdata` START), and an L3 or gdb call recipe; EXP + claims.
  - Stop: two sessions; RDS group decoding is out of scope.
  - Falsifier: the traffic module takes location data only from the US `XMD` path in this build.
  - Claims: C-7590–C-7599

- [ ] **M8.H63 — Inject one traffic event and watch `RDSTM001`/`LCTBL001` being read**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.H62
  - Goal: Call the injection point of `docs/firmware/tmc-path.md` with one real location code of the EU card and record the file reads and the result — the firmware-side test a generated Polish `RDSTM001`/`LCTBL001` will have to pass.
  - Precheck: `docs/firmware/tmc-path.md` gives the call recipe; `python3 tools/rdstm_place.py --help` works.
  - Scope: L3 first (`tools/l3_harness`), L4 through gdb if L3 lacks state; one location code present in the table and one absent.
  - Input: `docs/firmware/tmc-path.md`, `tools/rdstm_place.py`, `tools/lctbl_records.py`, `tools/read_watch_l3.py`.
  - Done when: for the present code the run reads the `RDSTM001`/`LCTBL001` ranges that `tools/rdstm_place.py` predicts and returns a place; for the absent code it returns the not-found path; new target in `tools/l3check.py` or a recipe in the EXP; `docs/research/reader-coverage.md` rows 21–22 updated.
  - Stop: if the event is dropped before the lookup (no tuner state), record the gate and stop.
  - Falsifier: both codes take the same path.
  - Claims: C-7600–C-7609

- [ ] **M8.H64 — First generated card at L4: the P0 card (one tile with OSM roads) against the factory card**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M8.H13
  - Goal: M8.E4 (full `Navi.exe` on a generated card) is one big acceptance run. Its first slice needs no screen: boot the P0 ladder card and the factory card through `tools/l4check.py` and compare stage, launcher verdict and files read.
  - Precheck: `python3 tools/card_ladder.py steps --check` names the P0 card recipe and `python3 tools/l4check.py --selftest` passes.
  - Scope: EU2011: build the P0 card as the ladder says (in-place patch, `tools/imgpatch.py`), run both cards, diff the verdict JSON; no position change, so the changed tile may not be read — state it.
  - Input: `tools/l4check.py`, `docs/research/card-ladder.md`, `tools/imgpatch.py`, `tools/ze0_sdtrace.py` if merged.
  - Done when: `python3 tools/l4check.py --card P0CARD --json` exits 0 with the same stage as the factory card, and the EXP lists the differences in files read (expected: none before a position change); the F4 column of `docs/research/reader-coverage.md` gets its first non-empty cell or a dated note why not.
  - Stop: one session.
  - Falsifier: the P0 card is rejected at a stage the factory card passes (a real finding for M5: record the log line).
  - Claims: C-7610–C-7619

- [ ] **M8.H65 — `DebugShell.dll` on `SCI6:`: the command list, and typing commands into the running emulator**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: The firmware carries a debug shell on the console line. If it accepts commands in the retail build, the emulator gets a control channel inside the guest (process list, memory, perhaps file and map commands) once serial RX works (M8.H1).
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all DebugShell` finds the module and `SCI6:`.
  - Scope: static, EU2011: is the shell started in the retail configuration (registry, launcher table), its command table (name, handler VA, help text), what input it needs. Live test only if M8.H1 is merged — otherwise the static table is the result.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/cehive.py`, `tools/applaunch_table.py`.
  - Done when: `docs/firmware/debugshell.md` with the command table and the start condition; if M8.H1 is on `main`, one command typed over the `sci6` chardev and its output quoted in the EXP.
  - Stop: one session.
  - Falsifier: the command table has no reference from any code (dead data).
  - Claims: C-7620–C-7629

- [ ] **M8.H66 — `serial_scif.dll` receive path: per channel, interrupt or DMA, and what an emulator must raise**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: reader
  - Depends: —
  - Goal: M8.H1 has to deliver received bytes the way the driver expects. Transmit on channel 10 is known (M8.C2a); receive is not. Read it once so the patch is written against facts.
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --image-start 0x3e00200 --encoding all Scif3SendThread` finds the driver; EXP-2026-11-22-M8.C2a-serial-dma names the TX channel.
  - Scope: static, EU2011: for SCIF 0–8 the receive mechanism (FIFO-trigger interrupt with INTEVT, or HPB-DMAC channel with its request source), the registers polled, error-flag handling, and the per-port configuration table in the registry.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `tools/cehive.py`, EXP-2026-11-22-M8.C2a-serial-dma, EXP-2026-11-20-M8.C1-hpb-dmac.
  - Done when: an EXP table channel → RX mechanism → interrupt/DMA channel → VA, covering at least SCIF 1, 3, 7 and 8; `docs/research/qemu-connectors.md` links it; `python3 tools/fn_audit.py`-style VA checks pass in `tools/gate.py`.
  - Stop: one session.
  - Falsifier: two channels of the same driver instance use different mechanisms with no configuration value selecting them.
  - Claims: C-8110–C-8119

- [ ] **M8.H67 — Watchdog and reset on `-M ze0` (row C22): who kicks what, and what a reset request looks like**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: model
  - Depends: —
  - Goal: Nothing models a watchdog; a guest that resets itself today shows up as an unexplained hang or restart. Find the watchdog (SoC WDT or the microcontroller's), the kick path, and the software reset path (used after updates and on fatal errors).
  - Precheck: `python3 tools/ce_strfind.py archive/head256.img --encoding all Reset WDT Watchdog` prints candidates in `nk.exe`/`PowerMonitor`.
  - Scope: static, EU2011 kernel B and `PowerMonitor`: registers, kick period, the reset request (register write or micon frame); then a logging stub patch `ze0-h67-wdt-log.patch` only if the block is on-chip.
  - Input: `tools/sh4dis.py`, `tools/sh4xref.py`, `docs/research/full-system-emulation.md`.
  - Done when: an EXP with the kick and reset paths (VAs) and, when on-chip, a boot log line per kick and a clean QEMU reset on a reset request (`-no-reboot` exits with a message).
  - Stop: one session.
  - Falsifier: no periodic write to any timer-like register exists outside TMU.
  - Claims: C-8120–C-8129

- [ ] **M8.H68 — `tools/ze0_ps.py`: process, thread and module list of the running guest from kernel structures**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: Several tasks need 'is process X running, what is thread Y waiting on' (M8.H47, M8.H45). CE 5 keeps fixed-layout kernel tables; read them from guest memory over the monitor or gdbstub.
  - Precheck: `python3 tools/ze0_screenshot.py --help` shows the monitor/pmemsave access to reuse; the CE 5.0 kernel data page address is in the kernel's ROMHDR/`KDataStruct` (`tools/cerom.py`).
  - Scope: process table (name, handle, base), per-process module list, thread list with state and current PC mapped to module; EU2011 kernel B; `--selftest` on a synthetic memory image.
  - Input: `tools/cerom.py`, `tools/ze0_screenshot.py`, `tools/qemu-ze0/gdb-ze0.py`, EXP-2026-11-20-M8.E2-registry-loaded.
  - Done when: `python3 tools/ze0_ps.py --monitor SOCK` on an idle EU2011 guest lists `nk.exe`, `filesys.exe`, `device.exe`, `Navi.exe` with thread counts; `--selftest` in `tools/selftest.py`.
  - Stop: one session; if the structure layout differs from public CE 5.0 headers, document the offsets found and stop at the process list.
  - Falsifier: the listed process names do not match the launcher's DBGMSG lines of the same run.
  - Claims: C-8130–C-8139

- [x] **M8.H69 — Breakpoints by name: a symbol file for the guest from `.pdata` and exports**
  - Status: done · Owner: task/m8.h69-symbols · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: Debugging the guest means typing VAs from EXP records. Generate a symbol table (module + export name, or `module!fn_VA`) for every module of a card's ROM images so gdb scripts and coverage reports use names.
  - Precheck: `python3 tools/nk_decomp.py pdata --help` and `python3 tools/cerom.py --help` work; `tools/qemu-ze0/gdb-ze0.py` loads in a Python-enabled gdb or the RSP client noted in project memory.
  - Scope: `tools/ze0_syms.py IMG -o syms.json` (per build: module, base, function starts, export names, known names from `docs/format/` tables), a lookup command (`addr → name`, `name → addr`), and loading in `gdb-ze0.py`; `--selftest`.
  - Input: `tools/cerom.py`, `tools/pdata.py`, `tools/fptables.py`, `tools/rom_atlas.py`, `tools/qemu-ze0/gdb-ze0.py`.
  - Done when: `python3 tools/ze0_syms.py archive/head256.img lookup 'Navi.exe!…'` resolves the `MMAIN001` reader VA of `docs/research/reader-coverage.md` both ways; `--selftest` in `tools/selftest.py`.
  - Stop: one session.
  - Falsifier: a function start from `.pdata` resolves into the wrong module (overlapping DLL ranges of A and B/C, known from M8.C1d).
  - Claims: C-8140–C-8149
  - Result: EXP-2026-11-22-M8.H69-symbols; mmain_reader resolves 0x0041a438 both ways; verify 0 missing owners; 36/36 tool selftest, 198/198 registry

- [x] **M8.H70 — A renamed street on the emulated screen: one map label changed in place, factory vs changed card at L4**
  - Status: done · Owner: claude/project-thread-66ezlk · Critical: yes · Pair: solo
  - Step: tooling
  - Depends: M8.C1f (done)
  - Goal: Marek (2026-11-22): "Skoro już odpala nam się w qemu mapa londynu na NAVI, to moglibyśmy zbudować zmodyfikowany obraz karty SD z podmienioną nazwą ulicy, i zweryfikować czy się podmieniła?" The first card change that the real `Navi.exe` has to draw: rename one street label visible on the M8.C1f London screen, patch the card in place, boot both cards and compare screenshots.
  - Precheck: `tools/ze0_screenshot.py screen` gives the London map on the factory EU 2011 card (EXP-2026-11-22-M8.C1f).
  - Scope: EU 2011 card, the `MAPAL001` tile that holds central London; same-length rename of one street name in the tile's zlib record streams (`1=NAME` entries), each changed stream recompressed to its original compressed length, written with `tools/imgpatch.py` (same length, no FAT change); a tool with `--selftest`; screenshots before/after kept out of the repo (manufacturer data).
  - Input: `tools/imgpatch.py`, `tools/ze0-viewer/ze0_decode.py` (`parse_names_section`), `tools/ze0_screenshot.py`, `tools/qemu-ze0/run.sh`, EXP-2026-11-22-M8.C1f-2dg-interpreter.
  - Done when: the changed card boots to the same map position and the screenshot shows the new name where the factory card shows the old one, every other label unchanged; the card SHA-256 and the changed streams are in the EXP.
  - Stop: one session; if the label does not change, find which file the renderer takes street labels from and record it.
  - Falsifier: the changed card shows the old name (the label comes from another file) or the map stops drawing (a record check the format docs do not know).
  - Claims: C-8220–C-8229
  - Result: EXP-2026-11-22-M8.H70-street-rename-l4; AIR STREET -> ARI/TIR STREET drawn by Navi.exe at L4, OSM STREET dropped (label wider than segment); tile_rename.py selftest 14/14

- [x] **M8.H71 — OSM roads on the emulated screen: one level-1 London parcel generated from OSM, factory vs generated card at L4**
  - Status: done · Owner: claude/project-thread-66ezlk · Critical: yes · Pair: solo
  - Step: tooling
  - Depends: M8.H70 (done)
  - Goal: Marek (2026-11-22): "jak byśmy sobie wygenerowali mapę z OSM, to moglibyśmy ją testować w Qemu - na obszarze londynu ... tak, ruszaj". The `-M ze0` start position is central London; until a GPS connector moves it, a generated London parcel is the only way to put our own geometry on the real `Navi.exe` screen.
  - Precheck: M8.H70 recipe boots the EU 2011 card to the London map; `download.bbbike.org/osm/bbbike/London/London.osm.pbf` is reachable from the sandbox.
  - Scope: EU 2011, tile `B48R068R`, level-1 directory `(77,923)`, the parcel under the start screen; `one_tile_pipeline.py --level 1 --clip` (roads only, `--no-names`, provisional-v0 classes), tile + `DRSTR001.DAT` patched with `imgpatch.py`; screenshots kept out of the repo.
  - Input: `tools/one_tile_pipeline.py`, `tools/imgpatch.py`, `tools/ze0_screenshot.py`, EXP-2026-11-22-M8.H70-street-rename-l4.
  - Done when: the generated card boots to the same position and the screenshot shows the OSM road network in the parcel; L1 (`cardcheck --image`, `imgpatch --check-diff --allow-metadata` outside 0) passes; the EXP records card SHA-256, changed pairs and what differs on screen.
  - Stop: one session; if the map stops drawing, record the last serial line and stop.
  - Falsifier: the screen shows the factory roads (the renderer does not read the changed parcel) or no roads in the parcel (records rejected).
  - Claims: C-8310–C-8319
  - Result: EXP-2026-11-22-M8.H71-osm-roads-l4; OSM London parcel drawn by Navi.exe at L4 (no names: --no-names); L1 PASS; pipeline negative-lon bbox fix

- [ ] **M8.H72 — Trigger the route simulation under ze0 to get a moving position**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M8.H21 (done)
  - Goal: M8.H21 found a demo/simulation mode in both 2011 builds: the `Navi.exe` menu item `2: Simulation on/off` (`fn 0x003daf5c`), the demo flag `u16 0x00bcd208`, `RGD_DEMO_*` position feeders (`fn 0x005182e0` …), `CRouteSimulation` in `NaviRouteCC.dll` (`fn 0x02f69198`) and the `NAVI_ROUTE_SIMULATION_START/PAUSE/STOP` events (`fn 0x004b9fa4`). If any trigger works under `-M ze0`, the emulator gets a moving position with no GPS/CAN sensor model — a moving test oracle for generated OSM cards.
  - Precheck: `tools/ze0_screenshot.py screen` boots the factory EU 2011 card to the London map (M8.H70/M8.H71); the M8.H21 VAs are readable in `archive/head256.img`.
  - Scope: EU 2011, image A; try the debug-menu selection `'2'` (value `0x32` at `0x003daf86`) and/or the `NAVI_ROUTE_SIMULATION_START` event; trace the position written by the `RGD_DEMO_*` helpers and `CRouteSimulation::ControlRouteSimulation`, using `tools/sh4dis.py`/`tools/sh4xref.py` to place breakpoints. The persistent switch may be `OBJ_Setting_readShopDemo` (`OBJDLL.dll` VA `0x034b7b84`). Keep screenshots and logs out of the repo; record only VAs, counts and hashes.
  - Input: `tools/qemu-ze0/run.sh`, `tools/ze0_screenshot.py`, `tools/sh4dis.py`, `tools/sh4xref.py`, EXP-2026-11-22-M8.H21-demo-drive.
  - Done when: an EXP records an L4 `-M ze0` run in which the simulated position changes on successive reads (a concrete position variable or the on-screen marker), naming the exact trigger, the position-feeding VA and the runnable harness command; the falsifier and the run's serial lines are in the EXP.
  - Stop: one session.
  - Falsifier: after the trigger the position never changes (the simulation needs the missing microcontroller/CAN input) — record the serial lines and stop; a `blocked` result is acceptable.
  - Claims: C-8380–C-8389
  - Pair: required
  - Note: follow-up from M8.H21 (verdict `present`). L4 integration input; needs a reviewer.

- [x] **M8.C1o — 2DG engine: decode and draw the remaining `0xb1`/`0xb3` commands**
  - Status: done · Owner: task/m8.c1o-2dg-ops · Critical: no · Pair: solo
  - Step: model
  - Depends: M8.C1f
  - Goal: Marek asked (2026-11-22) to improve the 2DG engine where we can. M8.C1f left 7 commands skipped (`0xb3007602` ×5, `0xb10038c2` ×2, C-6936). The emitters in build B `auirtdll.dll` (fn `0x03d0b408`, `0x03d0b502`) and build A `XGLDLL.dll` (fn `0x031204ac`, `0x031205a4`) give their exact header layouts; a `gfx-trace` dump gives the runtime operands.
  - Precheck: with `ze0-0014` and `gfx-trace=on` the map run logs `ze0-2dg: list …: N drawn, 7 skipped`.
  - Scope: `tools/qemu-ze0/patches/` (extend `ze0-0014` or add `ze0-0016`), an EXP record and claim rows. Decode the exact command lengths and the colour/width source; draw the primitives or, if their state is unrecoverable, advance by the exact length and record the missing piece.
  - Input: EXP-2026-11-22-M8.C1f-2dg-interpreter (O2, O5), the emitter disassembly of both builds, the new `gfx-trace` dump.
  - Done when: an L4 map run reports 0 skipped 2DG commands and the newly drawn pixels match the factory screenshot, or the EXP pins the layouts and names the state that cannot be recovered.
  - Stop: one RE pass plus one boot; if the colour source is a register never written in the lists, record it and stop.
  - Falsifier: after the change the screenshot loses map pixels or the guest error count grows.
  - Claims: C-8390–C-8399
  - Result: EXP-2026-11-22-M8.C1o-2dg-line-variants (C-8390–C-8395). ze0-0016 draws 2DG op 0xb1 (6-word header + inline vertices, count in word 4 low half) and 0xb3 (pointer form [op,N,OFF], vertices at op+OFF, colour from reg 0xf0) as polylines with exact lengths; both layouts read from build-A XGLDLL.dll fn 0x031204ac/0x031205a4 and build-B auirtdll.dll fn 0x03d0b408/0x03d0b502 and checked against a gfx-trace dump. L4 map boot: 2676 drawn / 0 skipped (was 2669 drawn / 7 skipped, C-6936); 342/384000 screenshot pixels differ (0.09%), no map pixels lost. UI layer and 0xb2/0xb4-0xb7 remain open.

---

## M9 — L3 toolkit: run firmware functions against our data

Design: [`docs/research/l3-ghidra.md`](docs/research/l3-ghidra.md). Code
lives in **`tools/l3_harness/`** (exists: `manifest.py`, `stubs.py`,
`rommap.py`, `runner.py` with `check`/`plan`; `run` is blocked). Pure-Python
parts are covered by `tools/l3_harness/selftest.py`.

- [ ] **M9.2 — Ghidra project builder**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (Ghidra
  - Step: tooling
  - Note (H112, 2026-11-19): priority raised by this pass. Three open questions (M3.25 reply path, M4.40 receiver, M3.28 name builders) are each a few hours in a decompiler and days in `sh4dis`. Import `Navi.exe` with the M1.20 pdata starts as function starts and the C-4624 import names; export the decompile of `0x00409ba0…0x0040b8b4` (37 functions, the map client API) and `0x003f1640`, `0x003fbed8`, `0x004011a0` first.
  - Note (H101, 2026-11-17): **runnable on Marek's host** (the agents run there; only the Claude sandbox lacks Ghidra). A decompiler is the largest single speed-up available for M3.26, M4.40 and every reader task: with `pdata` the function boundaries are exact, so import `Navi.exe` sec0 at `0x00011000` (SH-4 **little-endian**), create functions from `pdata.py table --json`, name imports from `cerom.py imports`, and export one `.c` file per function of the file layer (`0x00417d00…0x0041cab0`) and of the two 48-function tile subtrees into `archive/work/` (vendor-derived: never committed).
    cannot be installed in the Claude sandbox; the tool and `--plan` are done)
  - Depends: M9.1 (M1.6b for thunk labels)
  - Goal: `tools/l3_harness/ghidra_import.py` (pyghidra, headless): all
    A + B sections at their VAs, exports named, thunks labelled, SH-4
    calling convention.
  - Done when: Ghidra shows `OBJDLL!MAL_DataVol_getOffset` at the EXP-50
    call sites and the `HDD_INFO` string xref at `0x004e7d28` (this also
    closes the M1.5 Ghidra check).
  - Precheck: `python3 tools/l3_harness/ghidra_import.py --selftest` passes, and on the runner `command -v analyzeHeadless || python3 -c 'import pyghidra'` succeeds (in the Claude sandbox it fails: that is the `Runner: non-Claude` reason).
  - Scope: `tools/l3_harness/ghidra_import.py` and its plan; the Ghidra project and every exported decompile live in `archive/work/` (vendor-derived, never committed). Build A (EU2011) `Navi.exe` first, then the A + B sections the Goal names.
  - Stop: if Ghidra 12.2+/pyghidra is absent on the runner, the tool exits 3 `MISSING_GHIDRA` and the task stays `open` for a non-Claude runner; if the import runs but the two Done-when anchors are missing, record which section/VA is unmapped in an EXP and set `blocked`.
  - Blocker: Ghidra 12.2+ and the vendor image are absent; the tool writes and
    validates the two-phase plan (`--plan`, 13 checks) and exits 3
    `MISSING_GHIDRA`. Result: EXP-2026-11-06-M9.2-ghidra-import, C-1640.
  - Claims: C-1640–C-1649

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

- [x] **M9.10 — L3: decode the US POI with the firmware's own reader (software S2)**
  - Status: done · Owner: task/m9.10-us-poi-name-l3 · Critical: yes
  - Note (M9.33, 2026-11-20): prerequisite map — `READY`: US VAs (M1.22), name accessor (M3.11c) and byte order (M3.11b, firmware swap = `swap16`, C-5815) are met; what remains is this task's own runner and M9.55's `l3check` row (C-3403, EXP-2026-11-20-M9.33-rerun-prereqs-map).
  - Step: P4
  - Note (H51, 2026-11-11): the walker and accessor VAs are **EU-build** addresses; the US card carries a different `Navi.exe` (H51). The EU-code run stays as a method check; the gate for S1/S2 is the same run on the US build after **M1.22** gives the US VAs.
  - Note (M1.22b, 2026-11-16): the US VAs now exist and are **justified**, not voted: the POINT walker `0x003f5194 → 0x0041db44` (`DIFFERENT`, one pool word `0x4e8→0x4d8`, C-362x) and the POI name accessor `0x003f632c → 0x0041ec8c` (`UNIQUE`). Register the target with `build: "us2011"`; the run itself stays M9.10.
  - Note (M1.22, 2026-11-17): the US VAs are now **runnable**: `tools/point_walk_l3.py walk|skip --build us2011` runs the US nth reader (`0x0041db44`), skip walker (`0x0041c370`) and dispatcher (`0x0041e63c`) on `archive/us256.img` and passes 9/9 plus the guard/count controls on the US `POINT010` page (C-3534). Register the target with `build: "us2011"`; the chunk side is `cmp_ind_reader_us2011` in `targets.json` (C-3538).
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
  - Result: EXP-2026-11-20-M9.10-us-poi-name-l3. `runner.py run poi_record_decode` (new program `point_name_v1`, US2011 accessor `0x0041ec8c`) returns `HANA HEALTH CENTER` on the factory `POINT010` page `0x840ba0` and `OSM2LEAF TEST POI1` on the pair `mutate_refer_poi.py` wrote; 1,000/1,000 records per page split into name + address like their display text; stub log = `OSMDLL!taskIdSelf` only. Controls: wrong expected name `MISMATCH`, EU image `FAIL (wrong build)`, 7-field dictionary `REJECT`. `len2` control: the Python parser refuses a raised `len2`, the firmware does not (name still returned, walker 4 bytes late) — keep `parse_page` as the writer's gate. A synthetic corpus page makes the row runnable in `l3check --build-corpus` (`pass=3 runnable=3/13`). C-2140–C-2149. `--card` wiring stays with M9.12.

- [x] **M9.11 — L3: the firmware's chunk decoder on our recompressed `.cmp` (software S1)**
  - Status: done · Owner: task/m9.11-cmp-ind-reader-closeout · Critical: yes · Pair: pair
  - Result: EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md (reconciles EXP-2026-11-08-M9.11-chunk-decoder.md / M9.11b). `chunk_decoder_l3.py` and `runner.py cmp_ind_reader` (`firmware_call`, declared sec1 `inflate_mask[17]` at `0x574de0`, provenance explicit, no silent default) return page `0x840ba0` byte-identical to `cmpind.decode` for factory/S1/S2 POINT010 pairs; `--mutate corrupt-ind` rejected (`r0=-1`); `--mutate swap-4-8` fails cleanly (`r0=65536`). `cmp_ind_reader` registered in `targets.json` (M9.11b). Sec1-byte equality remains HYPOTHESIS (M1.2f). L3 fragment scope (chunk decode), not full `.ind` parser/opener or M9.12 `l3check --card` corpus acceptance.
  - Note (rule 15, 2026-11-09 PO): M9.11b done (firmware-call entry kind); re-opened then closeout-verified 2026-11-09. Prior blocker resolved: registration filled by M9.11b; sec1 inflate table (`0x574de0`, `inflate_mask[17]`) provenance explicit/declared, no silent default; sec1 bytes not read from decompressed sec1 (M1.2f open).
  - Note (M9.32, 2026-11-19): re-run through both registered targets (`cmp_ind_reader` EU2011, `cmp_ind_reader_us2011` US2011 after the runner build-routing fix): 3 pairs + 2 controls PASS each; EXP-2026-11-19-M9.32-reconcile-m9.11.
  - Depends: M9.5, M5.13b (the S1 pair). M3.2b is **no longer** a dependency.
  - Precheck: (reconciled 2026-11-09) `chunk_decoder_l3.py --selftest` and `runner.py selftest` pass; `runner.py run cmp_ind_reader --dry-run` shows declared sec1 table; `l3_precond.py --target cmp_ind_reader` reports READY (mitigated by declared sec1 input). M9.11/M9.11b/closeout EXPs reproduce factory/S1/S2 + controls on local M5.13b pairs/IMG256 (hashes recorded; vendor data outside repo).
  - Goal: prove in software what S1 would prove in the car: the firmware's own
    zlib + chunk loop accept our recompressed bytes and return the same
    logical page. Re-scoped in the sixth pass: `fn 0x0041c7dc` (M3.2b, C-2063)
    takes its 20-byte-stride chunk table from the caller, so the harness can
    build that table from `.ind` and never needs the `.ind` parser that lives
    in `Navi.exe` compressed sec1.
  - Scope: chunk-decode firmware fragment with declared sec1 table input and
    controls. Does not register full `.ind` parser/file-opener behavior and does
    not claim M9.12 `l3check --card` corpus acceptance.
  - Input: `fn 0x0041c7dc` (`@(28,ctx)` table; `+8` uncompressed offset, `+12`
    uncompressed length, `+16` compressed source, `+4` passed as r7), one-shot
    wrapper `0x542148`, `inflateInit2_ 0x542256`, `inflate 0x54233c`,
    `inflateEnd 0x54220c`; `runner.py` + `stubs.py`; the factory, S1 and S2
    `POINT010` pairs; `cmpind.py` decode as the reference page.
  - Done when: for all three pairs the firmware path returns page `0x840ba0`
    byte-identical to `cmpind.py` decode, one corrupt-`.ind` case is rejected,
    and one deliberately wrong table field (e.g. swapped `+4`/`+8`) is shown to
    fail — so the table layout is proven, not assumed. Fills the
    `cmp_ind_reader` target in `targets.json`. **(met 2026-11-09 closeout)**
  - Stop: n/a (satisfied). Future sec1-byte proof tracks M1.2f; corpus/card gate tracks M9.12.
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
  - Step: tooling
  - Note (M9.44, 2026-11-19): `python3 tools/vcard_l3.py boot` and `sweep` are a ready `--card` check for the file layer (mount verdict, table digest, every file read back through the firmware, `.cmp` through the firmware zlib): add them as the first two rows of the gate (C-4630, C-4651).
  - Note (H51, 2026-11-11): add a `--build us2011|eu2011` selector after **M1.22**: a US card is gated with US-build code. Until then report the build used in every verdict line.
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
  - Unblock: **M9.31** (no-diff/baseline verdicts for S0/S1) plus the
    remaining runnable targets (M9.10 POI, M9.6 map-code) so S0/S1 can produce
    runnable pass verdicts; then re-run and mark done. The `cmp_ind_reader`
    registration is done and no longer an unblock.
  - Result: EXP-2026-11-08-M9.12-l3check-card.md (C-2160 tool/behavior).
  - Claims: C-2160–C-2169

- [x] **M9.13 — L3 target `tile_reader` on factory and generated tiles**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes
  - Result: `docs/experiments/EXP-2026-11-20-M9.13-generated-tile-l3.md` (C-3250–C-3259); `tools/datask_l3.py mount --position LAT,LON` and `diff A.json B.json`. The firmware (EU2011, PySh4) reads the tile under the start position; at Krotoszyn (51.70 N 17.45 E) it reads `B48R058R`: header, 3 section tables, 5 directories. Factory tile against a `tilewriter.py --factory` tile with two OSM ways written in place in directory `0xa10b100`: **SAME** over 28 reads, and the firmware's slot-table parser loads the changed pair entries. Controls: directory header count 32 → 64 gives DIFFERENT; a changed pair entry gives SAME (the mount does not act on record lengths). The fresh-container tile of `one_tile_pipeline.py --synthetic` is **not readable**: its first directory read (`0x8100` bytes, a fixed length) runs past the 22 KiB file and fails. Not covered: road records (no record block is read before the mount stalls at state 2): M9.52, M9.53. The `targets.json` row stays `blocked` for `runner.py` and names this tool.
  - Step: P0
  - Note (M3.25, 2026-11-19): the entry is known and runs. Do not write a `(tile, dst)` wrapper: none exists. Use `python3 tools/datask_l3.py mount IMG256 --card-image CARD --replace MAPAL001/<tile>=<your tile> --json out.json` and compare the rows of that tile with the factory run: positions asked (they come from the 6-byte list at header `0x800`, C-4693), handler per read, bytes loaded. Verdict signals found so far: a directory read at a wrong position (C-4695), a level-table walk that runs past the table (C-4696), block header bits from `0x004144a8` (C-4692). `B28R070R` gets header + 2 directory reads at mount; for a data block either use a tile the mount reads blocks from (`B48R068R` here: the default position) or decode message `0x14b5`.
  - Blocker (resolved, kept as note): M9.20 added module entry kind / `engine_hook`; the original "only synthetic/blocked entry kinds" blocker is gone.
  - Re-opened (PO grooming 2026-11-09, rule 15): M9.20 merged. Prior negative EXP: EXP-2026-11-08-M9.13-reader-run. Expect possible re-block on compressed sec1 `.data`, unmapped globals, or file I/O stubs (M1.2f/M9.24) — record faulting PC if so.
  - Depends: M9.5 (M3.5 reader VAs `0x0041f26c`/`0x004259bc`/`0x0042757a`; M3.6 helps)
  - Precheck: `python3 tools/l3_harness/runner.py --selftest` passes with M9.20 module entry kind; M3.5 reader VAs resolvable via `cerom.py va2file`; compressed Navi.exe sec1/`.data` reader path accounted for (do not re-run as synthetic-only if firmware code/data path is unreachable).
  - Goal: run the real tile reader (M3.5) on one factory tile and on our round-tripped tile (M9.21) and compare the verdict.
  - Scope: register/repair a runnable `tile_reader` target once harness can call a module entry and required sec1/file I/O stubs exist; one factory and one round-tripped tile (M9.21). No new tile format claims.
  - Input: M9.21's round-tripped `B28R070R.DAT`; `runner.py run`, `stubs.py` (file I/O for `\SDMMC\MAPAL001\*.DAT`).
  - Done when: the reader returns a verdict for the factory tile and the same verdict (or a named, explained difference) for our tile.
  - Stop: if the reader path needs compressed sec1 data, unmapped globals, or file-I/O/import plumbing not yet modeled, block with the faulting PC/missing dependency and a new EXP — do not claim a reader verdict.
  - Claims: C-3250–C-3259

- [x] **M9.14 — L3 target `drstr_parser`**
  - Status: done · Owner: task/m9.14-drstr-parser-l3 · Critical: yes
  - Result: EXP-2026-11-20-M9.14-drstr-parser-l3; C-5940–C-5946 (block C-2240–C-2249 was used by the 2026-11-08 passes; this pass takes the fresh block C-5940–C-5949). The parser runs inside the firmware's mount (`vcard_l3.py boot`), now on both builds: `--build us2011` (13 layer functions paired by `fn_match`, 5 data addresses re-derived from the US literal pools by `vcard_l3.py port`; a head of the other build is refused). Factory `DRSTR001.DAT` ACCEPT on EU2011 (40 dirs/285 files) and US2011 (20/189, equal to the file's own counts); our writer's output (`drstr_rebuild.py`: byte-identical, grown tile, US writer order) ACCEPT on both builds with the table following the content; truncated to `0x800` and a bad listing offset REJECT (state stays 1, error log `0x00440dac`/`0x004411d6` US = EU `0x00419048`/`0x00419472` moved). `targets.json` keeps `drstr_parser` as a `runner.py` BLOCKED entry whose reason names the command.
  - Note (M9.44, 2026-11-19): the parser runs inside `vcard_l3.py boot` with the firmware's own arguments and has 7 controls (C-4636, C-4637, C-4648, C-4649). Close this target as covered by M9.44 unless a `runner.py` entry is still wanted.
  - Note (M9.36, 2026-11-20): re-run done — on the corrected engine the M9.35 probe of `sub_00419350` stops at `BLOCKED STUB OSMDLL.dll!OSM_Malloc` (EU2011, guarded and `--init-from-image` maps); the old `UNMAPPED 0xfffffec6` stop was the H51 `mov.w R0,@(22,R15)` defect at `0x0041936c` (C-3581, EXP-2026-11-20-M9.36-rerun-probes-pysh4). Inside `vcard_l3.py boot` the parser runs to completion (C-3584).
  - Note (H51, 2026-11-11): re-run after H51 before anything else (**M9.36**): the `UNMAPPED 0xfffffec6` stop of M9.35 has the shape of the engine defect fixed in H51 (`mov.w R0,@(disp,Rn)` stored through `r0`) — HYPOTHESIS until re-run. `0x00419350` is a pdata `START` (length `0x334`, ends exactly at `0x00419684`).
  - Note (Rule 15, M9.35 done): load-model blocker removed by M9.35 (zero BSS + bound IAT + INIT guard). Prior blocked/re-open notes kept below. M9.35 IMG256 scratch probe of `sub_00419350` (EXP-2026-11-10-M9.35-sec1-load-model) gets past `0x0055d8fc` and stops at `UNMAPPED 0xfffffec6..0xfffffec8` (empty-args/context probe); rerun with proper context, M9.24 import/file stubs and M5.6 rebuilt DRSTR as needed for verdict.
  - Re-opened (ninth pass, rule 15): **M9.20 merged** (`562215a`) with the
    module entry kind and `engine_hook`, so the first blocker no longer holds.
    The reopened run (EXP-2026-11-08-M9.14-reopen) ran the module entry on the real head image:
    the reader's data is in compressed `sec1`, so it stops at once.
  - Depends: M3.10 (archived 2026-11-19, `docs/research/todo-history-2026-11-19.md`), M9.5 (both done)
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
    blocked on M1.2f/M9.24/M5.6 as applicable (do not guess verdicts). If a probe stops at `INIT 0x… (M1.2f)`, only that address needs M1.2f.
  - Claims: C-5940–C-5949 (was C-2240–C-2249; fresh block for this run)
  - Prior blocker (kept): `sub_00419350` read its coredll imports and buffer global from
    compressed `Navi.exe` `sec1` (UNMAPPED at `0x0055d8fc`); the Done-when also
    needs a DRSTR rebuilt by M5.6, which is open.
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker VA `0x0055d8fc` = IAT `OSMDLL!OSM_Malloc` (import/binding/stub, not M1.2f). Rerun with M9.35 + M9.24 (and M5.6 as applicable); M1.2f not needed for this VA.
  - Unblock: M9.35 done (H49). Next: M9.24 (import binding and coredll
    file stubs) and M5.6 for rebuilt DRSTR verdict.
  - Result: EXP-2026-11-08-M9.14-reopen (negative, controls: M9.20 point-walker
    reproduced, compressed and outside-VA negatives; no DRSTR verdict; C-2240–C-2243). M9.35 scratch probe: EXP-2026-11-10-M9.35-sec1-load-model (next stop `UNMAPPED 0xfffffec6..0xfffffec8`, past 0x0055d8fc).

- [ ] **M9.15 — L3 targets for `ADDRE`, `ZCODE`/`ICODE`/`COORD`, `LCTBL`**
  - Status: open · Owner: — · Critical: yes
  - Step: P3
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
  - Step: tooling
  - Note (PO 2026-11-20, 21st pass): most of this chain now runs on a card image instead of a tree: `vcard_l3.py boot`/`sweep` (`CMP.LST` → `MMAIN001` → `DRSTR001`, every file, EU2011 and the US2011 file layer, M9.14) and `datask_l3.py mount` (tiles and `REFER001`, EU2011, M9.13/M9.52/M9.53). What is left is two tasks, take those instead of this block: **M9.60** (one command with a verdict per step) and **M9.61** (the map client on the US build). This block closes when both are done; M8.E4 and M5.35 then name them directly.
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

- [x] **M9.17 — L3 target `mmain_reader` (H11 G1)**
  - Status: done · Owner: task/m9.17-mmain-reader-l3 · Critical: no
  - Result: EXP-2026-11-20-M9.17-mmain-reader-l3 (C-5970–C-5973). `tools/mmain_l3.py run` boots the EU card per case (`vcard_l3.py`): factory, `mmain.py`-rebuilt, edited (+1 count) and pipeline-generated `MMAIN001.DAT` ACCEPT with one `0x1000` read, buffer `0x00e23cc0` = `swap16(file)` and an equal `mmain.py` model; 4095-byte and absent REJECT (6/6). `targets.json` `mmain_reader` is a blocked entry naming the tool (the reader runs inside the mount, not as a `runner.py` call; no `corpus.py` row needed); matrix row 3 updated. EU2011 only.
  - Note (M9.44, 2026-11-19): `mmain_reader` runs inside `vcard_l3.py boot`; presence and a full `0x1000`-byte read are the only checks (C-4635). Close as covered by M9.44 unless a `runner.py` entry is still wanted.
  - Note (M9.36, 2026-11-20): re-run done — the M9.35 probe of `0x0041a438` executes no changed instruction and still stops at `BLOCKED STUB COREDLL.dll!wcstombs` on the corrected engine (EU2011, C-3582, EXP-2026-11-20-M9.36-rerun-probes-pysh4); inside `vcard_l3.py boot` the reader runs to completion (C-3584).
  - Note (H51, 2026-11-11): re-run on the corrected engine (**M9.36**) and with real `INIT` bytes (**M1.19**); `0x0041a438` is a pdata `START` (length `0xf4`).
  - Note (Rule 15, M9.35 done): load-model blocker removed by M9.35 (zero BSS + bound IAT + INIT guard). Prior blocked note kept: first data access was at `0x0055d040` (compressed sec1, UNMAPPED). M9.35 IMG256 scratch probe (EXP-2026-11-10-M9.35-sec1-load-model) gets past `0x0055d040` and stops at `BLOCKED STUB COREDLL.dll!wcstombs`; rerun with proper context/stubs (M9.24) needed for verdict.
  - Re-opened (ninth pass, rule 15): M9.20 merged (`562215a`); the module-VA
    entry it needs now exists.
  - Prior blocker (kept): the M3.8 reader ran as a module entry (M9.20) but its first data access was at `0x0055d040`, in `Navi.exe` section 1 (compressed, `rw-`), which the map skipped: `BLOCKED` UNMAPPED.
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker VAs `0x0055d040` = IAT `COREDLL!memset` and `0x00e23cc0` = BSS sec1 +0x8c6cc0 (zero at load; find writer/runtime init) — neither needs M1.2f. Rerun with M9.35 context.
  - Unblock: M9.35 done (H49). Next: M9.24 CRT/import/file stubs and proper args/context as needed; if a probe stops at `INIT 0x… (M1.2f)`, only that address needs M1.2f.
  - Result: EXP-2026-11-08-M9.17-reopen (negative: module run BLOCKED at a compressed `.data` access, controls PASS; C-2372–C-2373). Earlier block: EXP-2026-11-08-M9.17-m38-reader (C-2370–C-2371). M9.35 scratch probe: EXP-2026-11-10-M9.35-sec1-load-model (next stop `BLOCKED STUB COREDLL.dll!wcstombs`, past 0x0055d040).
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
  - Claims: C-5970–C-5979 (was C-2370–C-2379; fresh block for this run)

- [ ] **M9.18 — L3 targets for `LEV3456R` and the tile sections (H11 G8)**
  - Status: open · Owner: — · Critical: no
  - Re-opened (rule 15, PO 2026-11-20): M9.53 merged (#349) — `datask_l3.py mount --request MESH` reads and inflates a record block (C-5910–C-5917), so the record-level G/F pair below can run. The blocker line is kept as history.
  - Blocker (history): the mount reads no record block (state 2, `0x1507` undelivered), so coarse records and the section-4 name list cannot be compared; directory level is done.
  - Unblock (met): M9.53 (a map request reads a record block; then rerun the EXP's G/F pair at record level with `lev3456.py decode_record` / `section4.py parse`).
  - Result: EXP-2026-11-20-M9.18-lev3456r-sec4-l3 (C-2440–C-2446). New `tools/mount_dirs_l3.py` (`check`/`compare`/`changed`, selftest 11) checks each mount read against `lev3456.py`/`clarion_tile`: factory `LEV3456R` 9/9 and `B48R058R` 9/9 (incl. section-4 table + directory, parser `0x00415330`, typ `0x93`) MATCH; a `lev3456gen.py` file is SAME-RELOCATED; controls (L3 dir rows, s4 dir header, wrong model) MISMATCH. The level-3 directory read is the one under the start position (4 positions). Defect: `lev3456gen.py` writes L3 roads into the wrong directory (C-2445) → M5.59. Targets `lev3456_reader`, `tile_section4_reader` registered as blocked entries naming the tools; rows 18–20 updated.
  - Step: P2
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

- [x] **M9.24 — Module entries that call coredll file APIs: bind imports, stub the CRT file calls**
  - Note (M9.44, 2026-11-19): covered for the map-file layer: `tools/vcard_l3.py` has 81 import models (file, string, memory, printf, heap, task, object calls) and a card behind `fopen`/`fread`/`fseek`. What is left here is only reuse of those models from `runner.py` targets outside the layer; if no target needs that, close as covered.
  - Status: done · Owner: task/m9.24-coredll-file-apis · Critical: yes
  - Result: EXP-2026-11-20-M9.24-drstr-parser-runner (C-2640–C-2645). `runner.py run drstr_parser --image IMG256 --input DRSTR001.DAT` (new firmware_call program `drstr_parser_v1`, new `tools/drstr_l3.py`) runs EU2011 open wrapper `0x0041b3bc` → parser `0x00419350` → close `0x0041b650` with `vcard_l3`'s bound imports: factory file PASS, ACCEPT, r0 0, no fault, 16 imports all modelled. `verdict_map` `{0: ACCEPT, 0xffffffff: REJECT}` decoded from the parser's three exits (the runner BLOCKs any other map). Controls 9/9: `+36` not a multiple of 40 → REJECT code 20, `> 200` entries → code 10, size `> 0x77220` → code 26 but still parsed; a 32-byte file is ACCEPT (parsed from the buffer past EOF, zero heap).
  - Step: tooling
  - Note (H101, 2026-11-17): narrowed by **M9.44**: stub the firmware's three stdio wrappers (`0x0041b3bc`, `0x0041b470`, `0x0041b4f8`) instead of the coredll imports behind them.
  - Depends: M9.35 (done, H49: the import slots and BSS of sec1 need no decompression; M9.35 maps them)
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
  - Stop: if a fault lands on an address `tools/va_class.py` classes `INIT`
    (stored sec1/sec2 bytes), or coredll ordinals cannot be re-derived
    reproducibly, record the faulting PC/VA class and keep blocked on M1.2f
    for that address only; do not guess ordinals or verdicts. Ordinals:
    `cerom.py imports Navi.exe --resolve-with 0x3e00200` names them (H49).
  - Claims: C-2640–C-2649

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

---

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


- [ ] **M9.31 — `l3check --card` baseline/no-diff verdicts for S0/S1 (unblocks M9.12)**
  - Status: open · Owner: — · Critical: no
  - Step: tooling
  - Pair: solo
  - Depends: M9.41 (the US S1 evidence row this baseline needs), M9.11/M9.11b (cmp_ind_reader path), M9.6 context. **Was `M9.12 (blocked)`** — that made a deadlock: M9.31 unblocks M9.12 and M9.12's `Unblock:` is M9.31, so as written neither could ever be taken (SE 2026-11-17).
  - Goal: make the card gate produce runnable verdicts when S0/S1 are byte-identical to factory, instead of `NO_DIFFS`/exit 3 with no pass evidence. A no-diff card is a valid baseline and should still exercise registered runnable targets on factory/baseline files where safe.
  - Precheck: `python3 tools/l3check.py --selftest` passes; M9.12 EXP states the S0/S1 no-diff blocker and S2 PASS path.
  - Scope: add `--baseline` (or equivalent, name in PR) / no-diff handling to `tools/l3check.py`: when card==factory or selected diff set is empty, run registered runnable targets on the baseline/factory files they declare (or a documented minimal set) and report PASS/FAIL/SKIP/BLOCKED/not-yet-available; `NO_DIFFS` remains a distinct informational state only if no runnable target applies. Keep synthetic/vendor policy explicit. No silent PASS.
  - Input: `tools/l3check.py`, M9.12 EXP (`EXP-2026-11-08-M9.12-l3check-card`), `targets.json` target applicability metadata, `chunk_decoder_l3.py`/M9.11 path.
  - Done when: on a synthetic or documented fixture where card and factory inputs are identical, `l3check.py --card ... --factory ...` (with the chosen no-diff mode) runs at least the runnable M9.11/M9.6-equivalent paths available in that fixture and reports explicit verdicts (not bare `NO_DIFFS`/exit 3 without verdicts), with selftest/EXP evidence; M9.12 can cite it as the S0/S1 unblock path.
  - Stop: if no registered runnable target can declare a safe baseline corpus, report `NO_RUNNABLE_BASELINE_TARGETS` with reasons and keep M9.12 blocked (do not fabricate verdicts).
  - Claims: C-3320–C-3329

- [x] **M9.41 — M9.10's last US-build gap: `point_walk_l3` runs the US reader but the target is not registered as an S1/S2 evidence row**
  - Status: done · Owner: task/m9.41-us-poi-row · Critical: yes · Pair: required
  - Blocker: the Done-when needs a `--build-corpus` row that is **runnable with its verdict**, but `runner.py` dispatches only `cmp_ind_chunk_v1`/`mapcode_compare_v1` (`unknown firmware_call program` otherwise) and `l3check --build-corpus` never passes `--image/--cmp/--ind`, so a POINT target added exactly within the Scope is BLOCKED; making it runnable needs `runner.py`/`l3check.py`/`corpus.py`, outside the Scope (EXP-2026-11-20-M9.41-us-poi-row, C-4223–C-4225).
  - Unblock: M9.55
  - Depends: M9.10 (the US `point_walk_l3` run exists), M1.22 (done — US VAs), M9.39 (a record-mutated page is the control), M1.22b (done — the US VAs are justified)
  - Goal: give the US POI walk that M1.22 already runs a registered L3 target and `l3check` evidence row, so rule-13 S1/S2 acceptance for the US POI path is a gate row instead of prose in an EXP.
  - Note (SE 2026-11-17): M1.22's Result and its note on M9.10 say the US walker now runs 9/9 plus guard/count controls on `archive/us256.img`, but M9.10 still reads "name part waits for M3.11c" and nothing in `targets.json`/`l3check.TARGET_EVIDENCE` names the US `point_walk_l3` run. This task is **not** M9.10's `poi_record_decode` runner target (M9.10 ports the walk into `runner.py` and adds the name check); it is the cheaper C-3538-shaped move: register the *existing* `point_walk_l3 --build us2011` run as a `targets.json` evidence row so `l3check` reports it and M9.10 can cite it. Its Scope and files do not overlap M9.10's runner work.
  - Precheck: `python3 tools/point_walk_l3.py walk --build us2011 --cmp <US POINT010.DAT.cmp> --ind <…ind> --page 0x840ba0 --page-len 42848 archive/us256.img` prints `result: PASS` (I ran it on the S1 tree's `POINT010` and got `n=999 … OK`, `result: PASS`); `grep -n 'point_walk_us2011' tools/l3_harness/targets.json tools/l3check.py` prints nothing today.
  - Scope: `tools/l3_harness/targets.json` + `tools/l3check.py` `TARGET_EVIDENCE` + `docs/research/reader-coverage.md` POINT row only: add the US walker target with its declared US VAs (from M1.22's tree, not retyped — C-3635-adjacent), point the evidence at M9.39's mutated page as the negative control, and tick the M9.10 name half only if the accessor (`0x003f632c → 0x0041ec8c`, C-3701-adjacent) also runs; otherwise state the name half still needs M3.11c. No new VAs; if one is missing, set `blocked` and name the M-task that derives it.
  - Input: `tools/point_walk_l3.py` (`BUILD_TARGETS`, `walk`, `skip`), `tools/l3_harness/targets.json`, `tools/l3check.py`, M1.22 EXP (`EXP-2026-11-17-M1.22-us-build-census`), M9.10/M9.39 blocks.
  - Hints: `targets.json` already has a `build: us2011` shape (`cmp_ind_reader_us2011`, C-3538); copy that shape, do not invent a second build field. `l3check --build-corpus` must stay `runnable=1/7` or grow by exactly one, and a `BLOCKED` row is not a pass.
  - Done when: `python3 tools/l3check.py --build-corpus` lists the new US target as runnable with its verdict, the `point_walk_l3 walk --build us2011 …` command in the precheck prints `result: PASS` with the M9.39 mutated page failing a control, `python3 tools/l3check.py --selftest` passes, and M9.10's Status/Result either cites the new row as its S1 evidence or states exactly which half is still open.
  - Stop: if the name accessor cannot run on the US build without M3.11c, register the walker row only, mark M9.10's name half open, and do not mark M9.10 `done`.
  - Falsifier: the target appears in `--build-corpus` but a wrong-*build* run (`walk archive/head256.img … --build us2011`) prints `result: PASS` instead of `result: FAIL (unmapped …)`; the M9.39 mutant page is a *positive* witness (it must still pass on its own build), never a negative control.
  - Claims: C-4220–C-4229
  - Result: `blocked` — EXP-2026-11-20-M9.41-us-poi-row (C-4220–C-4229). Not done: the Done-when's "`--build-corpus` lists the new US target as runnable with its verdict" needs `runner.py` dispatch for a POINT program (only `cmp_ind_chunk_v1`/`mapcode_compare_v1` exist: `unknown firmware_call program 'point_walk_v1'`) and `l3check.py` `--build-corpus` `--image/--cmp/--ind` plumbing — three files outside this task's Scope; a Scope-sized target is BLOCKED (C-4223–C-4225). Evidence the walk itself is sound is kept: factory + M9.39 mutant `result: PASS` on `us256.img` with `n=501 0xfe4e→0xfe52`, `n=998/999 +4`, count 1,000 (C-4221–C-4222); wrong-build `result: FAIL (unmapped …)`, exit 1, 0 tracebacks (C-4226). M9.10's name half stays open because the walker proves framing only (C-4178) and its name check needs M9.10's own `poi_record_decode` runner plus M3.11b's text byte order — the accessor itself already runs (US 1000/1000, C-5110–C-5112), not M3.11c which is done. Unblock: **M9.55**.
  - Re-opened (rule 15, M9.55 merged): its Done-when is met by the `point_walk_us2011` row (`l3check --build-corpus` `PASS`/`ACCEPT`, `runnable=2/9`, EXP-2026-11-20-M9.55-us-poi-runner, C-5770–C-5773); set `done` with that EXP as its Result, the walk half is S1/S2 evidence.

- [x] **M9.35 — sec1 load model: zero BSS, bind the IAT, fail loudly on `INIT`**
  - Status: done · Owner: task/m9.35-sec1-load-model · Critical: yes
  - Depends: — (M9.20 done; H49 gives the classes and `tools/va_class.py`)
  - Goal: a module run maps what the CE loader would: `Navi.exe` sec1 as a zero-filled `rw-` block (`0x0055d000`, vsize `0xff16ae`), the 846 import slots holding stub-trampoline VAs that report `DLL!name` when called, and any read of an `INIT` byte (sec1 `0x0055dd38…0x0057501a`, sec2) stopping as `BLOCKED INIT 0x… (M1.2f)`. This replaces "UNMAPPED in compressed sec1" for M9.17/M9.14 and is the base for M9.24's real CRT stubs.
  - Precheck: `python3 tools/va_class.py IMG256 --module Navi.exe --resolve-with 0x3e00200 0x0055d040 0x0055d8fc` → `IAT memset`, `IAT OSM_Malloc`; `python3 tools/l3_harness/runner.py selftest` passes.
  - Scope: `tools/l3_harness/rommap.py` (a `--bss-zero` / `--init-guard` mode using `comphdr` `uncompressed_len`), `runner.py`/`stubs.py` (IAT trampolines with names from `cerom.imports` + `--resolve-with 0x3e00200`; an unknown import stops as `BLOCKED STUB DLL!name`, never a silent return). No guessed `INIT` bytes; no verdict maps.
  - Input: EXP-2026-11-10-H49-pm-review, EXP-2026-11-08-M9.17-reopen, EXP-2026-11-08-M9.14-reopen, EXP-2026-11-08-M9.20-l3-plumbing.
  - Done when: selftest covers zero-BSS read, a bound-IAT call reaching a named stub, an unbound import → `BLOCKED STUB`, and an `INIT` read → `BLOCKED INIT`; the M9.17 `mmain_reader` scratch run and the M9.14 `drstr-sub_00419350` run on IMG256 get past `0x0055d040`/`0x0055d8fc` and report their **next** stop (stub name or faulting PC + class) in an EXP (tests C-3445). Rule 15: on merge, set M9.17/M9.14 back to `open` and M9.24's Depends to done.
  - Stop: if the run stops on an `INIT` address, record it with its class and stop — that address, and only that one, goes to M1.2f.
  - Claims: C-3450–C-3459
  - Result: `docs/experiments/EXP-2026-11-10-M9.35-sec1-load-model.md` (C-3450–C-3458). `rommap.py --bss-zero/--init-guard` + runner IAT trampolines/INIT guards implemented; 4 synthetic cases pass (`runner.py --selftest` 23/2 skipped quick, `l3_harness/selftest.py` 32/quick, `rommap.py --selftest` 32/quick, `va_class.py --selftest` 8). IMG256 guarded probes get past `0x0055d040`/`0x0055d8fc`: `mmain_reader` (0x0041a438) → `BLOCKED STUB COREDLL.dll!wcstombs`, `drstr-sub_00419350` (0x00419350) → `UNMAPPED 0xfffffec6..0xfffffec8` (scratch empty-args/context). Rule 15 applied: M9.17/M9.14 reopened, M9.24 Depends M9.35 done.

- [x] **M9.36 — Re-run every L3 probe and blocker on the corrected PySh4**
  - Status: done · Owner: task/m9.36-rerun-probes-pysh4 · Critical: yes
  - Result: EXP-2026-11-20-M9.36-rerun-probes-pysh4; C-3580–C-3587. New `tools/l3_harness/engine_exposure.py` (`changed`/`run`/`static`) counts the executed halfwords whose outcome differs between an old engine and `main`: 1,867 changed vs `116c826` (720 H51 forms + 1,147 later). Of 47 re-runs (every `targets.json` target, `point_walk_l3` walk/skip, `chunk_decoder_l3` factory/S1/S2/corrupt-ind/swap-4-8 on EU2011+US2011, M9.35/M9.20 probes, M9.6, M9.13 F, M3.11c, M9.44 boot + 2 controls) exactly one result changes: the M9.35 `drstr-sub_00419350` probe stops at `BLOCKED STUB OSMDLL.dll!OSM_Malloc`, not `UNMAPPED 0xfffffec6` — engine-only A/B on the `116c826` tree; the cause is `mov.w R0,@(22,R15)` at EU2011 `0x0041936c` (C-3489 verified, C-3455/C-3457 retracted). Every other verdict and counter reproduces; no run executes a form changed after H51. NOT RE-RUN: the M3.11c 2026-11-08 heredoc runs (static bound: 0 changed halfwords in the called leaves) and M9.13 G/C1/S (need `krotoszyn.osm`).
  - Depends: — (H51 engine fix is on `main` with this task)
  - Goal: until H51, `mov.b R0,@(disp,Rn)` and `mov.w R0,@(disp,Rn)` stored through `r0` instead of `Rn` — silently. Any earlier run that executed one of them wrote to a wrong address: an `UNMAPPED 0xffffffxx` stop is the visible form, a store into a mapped region is the invisible one. Find out which recorded L3 results change.
  - Precheck: `python3 tools/l3_harness/engine.py --selftest` shows the check "mov.b/mov.w R0,@(disp,Rn) base is Rn; mul.l any Rm; movca.l (H51)".
  - Scope: every target in `tools/l3_harness/targets.json`, `point_walk_l3.py` (`walk`, `skip`), `chunk_decoder_l3.py` (factory, S1, S2, `corrupt-ind`, `swap-4-8`), the M9.35 probes (`mmain_reader`, `drstr-sub_00419350`), M9.6, M9.13, M9.20 and the sub-accessor runs of M3.11c. Before/after on the same inputs.
  - Input: the EXPs of those tasks give the commands; `git stash`/a worktree at `116c826` gives the old engine for the "before" column where the EXP has no number.
  - Hints: `drstr-sub_00419350` stopped at `UNMAPPED 0xfffffec6..0xfffffec8` (M9.35) — a 2-byte store just below zero is exactly what `mov.w r0,@(disp,Rn)` with a small negative `r0` produced; expect that stop to move. To see whether a run is affected without re-running it, count the opcodes `0x80xx`/`0x81xx` in the functions it executes (`sh4dis` + pdata length).
  - Done when: an EXP table `target / input / before / after / changed?`; every changed verdict is corrected in its task block, `reader-coverage.md` and `claims.md`; M9.14 and M9.17 carry the new next stop.
  - Stop: a target that needs corpus files not obtainable in the session is listed `NOT RE-RUN` with the reason.
  - Claims: C-3580–C-3589

- [x] **M9.38 — Read-watch tracer: which functions read the page buffer**
  - Status: done · Owner: task/m9.38-read-watch · Critical: yes
  - Result: EXP-2026-11-19-M9.38-read-watch; C-3600–C-3609. `engine.PySh4` records guest loads/stores in-body with `api`/`x` tags and arms after setup (inert: watch-on vs watch-off `IDENTICAL` on `r0`, OUT SHA-256, `sec_reads`, insns); `watch.py` GAP-labels attribution; `read_watch_l3.py` runs `walk`/`above`/`chain`/`probe`. POINT reader = the walker leaf `0x003f5194`/`0x0041db44` via the real dispatcher `0x003f5cdc`/`0x0041e63c`; the `.cmp` caller `0x0041c044` is decode-only (destination never read); ADDRE readers `0x003fbed8`/`0x003f9254`/`0x004125a8`; LCTBL reader `0x0040de98`. Lists handed to M3.11b/M3.13/M3.15.
  - Note (SE 2026-11-13): `777fb68` named this task in its subject but changed only `pdata.py`/`fn_match.py`; `engine.py` has no `watch(range, kind=…)` hook and `runner.py` has no `--watch`. Nothing is claimed; take it after M1.20's pdata tool is wired (M1.23).
  - Depends: M1.20 (function names for PCs); M1.19 helps (real `INIT` bytes)
  - Goal: the dynamic counterpart of M3.23. Put a decoded factory page in a buffer, run a caller from the family's access path, and log every load from the buffer with its PC — attributed to a function. The functions that read the record bytes are the reader, whatever their code looks like.
  - Precheck: `python3 tools/point_walk_l3.py walk …` (C-2541) still passes — it is the positive control: the tracer must report `fn 0x003f5194` as the reader of the POINT page.
  - Scope: `tools/l3_harness/engine.py` gets `watch(range, kind='r'|'w')` hooks (off by default, no cost when unused); `runner.py run TARGET --watch NAME` prints `function / reads / first offset / last offset / widths`; a write watch on the same buffer answers M3.11b (who byte-swaps the POINT page — or shows that nobody does and the walker gets a copy).
  - Input: `chunk_decoder_l3.py` already wraps `eng._load` to log section reads — generalise that; the M9.35 load model (IAT stubs) for callers that reach imports; page `0x840ba0` of US `POINT010` as the first corpus, then one `LCTBL001` name page, one `ADDRE` shard page.
  - Hints: start high in the chain and let it run until the first unstubbed import: `fn 0x0041c044` (the `.cmp` caller found by H51) with a real `.cmp`/`.ind` pair mapped gives the decode *and* everything that touches the decoded page afterwards. Width matters: a reader that loads 16-bit big-endian fields byte by byte (`mov.b` ×2 + `shll8`) and one that loads `mov.w` from a swapped copy are the two answers M3.11b is choosing between.
  - Done when: the control passes; one run each for `POINT` (from above the walker), `LCTBL` and `ADDRE` lists the reading functions; M3.11b, M3.15 and M3.13 get the list in their blocks; the tracer has a selftest with a synthetic two-function program.
  - Stop: if a run ends at an import before any read of the buffer, name the import and add its stub to M9.24's list.
  - Claims: C-3600–C-3609

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


- [x] **M9.52 — Finish the firmware's mount in `datask_l3.py`: who answers message `0x1507`**
  - Status: done · Owner: task/m9.52-mount-1507 · Critical: yes · Pair: solo
  - Step: P1
  - Depends: M3.25, M9.13 (done)
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image <EU card> --max-reads 40` ends with `state 2` and a `not delivered: {"kind": "send", "task": 0, "id": 5383, …}` line (5383 = `0x1507`).
  - Goal: in every `datask_l3.py mount` run the data-access task stops with its state word (data VA `0xd62490`) at 2 and one undelivered send: message `0x1507` sub 1 to task id 0, sent by `0x00401e94` (C-4697). The receiver's id is read from a global nobody set, so the owning task is not part of the run. Until the mount finishes the dispatcher defers map requests (`0x14b5` has the defer flag, C-4681), so no record block of a tile is ever read (C-3259).
  - Scope: EU2011 `Navi.exe` only. (1) `sh4dis --va 0x00401e94`: which global holds the receiver id, what the message body is; (2) `sh4xref --to <that global>` and `callgraph.py callers` to find the task that owns the id and its handler for `0x1507`; (3) read what it sends back (id, sub, body) and which row of the message table (`datask_l3.py tables`) receives it; (4) add the reply as a model in `datask_l3.py` (a function that, given the logged send, produces the answer message) and report the state word and the progress word at data VA `0xd98fcc` (`0x003f7740` sets it to 5; the dispatcher wants 1).
  - Hints: the state machine is in `0x003f77cc` → `0x003f7740` → `0x003f7624`; `0x003f7740` takes the short path (`0x003f7624`) when the `u16` at data VA `0xd8b08c` is 1, else it sets the progress word to 5 and goes the long way. Find who writes that word (`sh4xref --to`) before trying the short path. Do not fake state 3 by writing the global.
  - Done when: a `mount` run ends with state 3 (or the EXP names the next message the mount waits for, with sender, receiver and the function that would answer); `--selftest` covers the reply model; EXP + claims.
  - Stop: if the answer needs a task whose code is outside `Navi.exe`, name the module and export and stop.
  - Falsifier: the state word reaches 3 without any reply (then the wait is on something else: say what).
  - Claims: C-5900–C-5909 (was none yet (take the next free block when claimed); fresh block for this run)
  - Result: `docs/experiments/EXP-2026-11-20-M9.52-mount-1507.md` (C-5900–C-5907). `0x1507` goes to `SDL_task` (id global `0x11fff50`, entry `0x0039d854`, EU2011), which drops it at its gate `0x003c009c` (it takes a data-access message only as the answer to its own pending request) and answers nothing; the mount does not wait for it. The only writer of state 3 is `0x003f6b1c`, object-store event `0x07d0` sub 11 with `+28 = 16`; `datask_l3.py mount --sdl --event 11:16` (stand-in event) ends with state 3, progress 1; controls `11:15`, `12:16` stay at 2. The subscriber that delivers event 11 is not found in `Navi.exe`: M9.57.

- [x] **M9.53 — Make the firmware read a record block we wrote: one map request through `datask_l3.py`**
  - Status: done · Owner: task/m9.53-record-block-read · Critical: yes · Pair: required
  - Step: P1
  - Depends: M9.52
  - Precheck: `python3 tools/datask_l3.py tables archive/head256.img` lists `0x14b5  1  0x004066ac`; M9.52's run ends with state 3.
  - Goal: M9.13 shows the firmware reads our tile's header, section tables and directories like the factory tile, but the road records (the zlib blocks `tilewriter.py` writes) are never requested during the mount, and a wrong pair entry goes unnoticed (C-3255). The gate rule 13 asks for is the firmware inflating and walking *our record*.
  - Scope: EU2011. Message `0x14b5` → `0x004066ac` → `0x0040638c` → `0x0040d4a0` → `0x0040b6b0` → read issuer `0x0040a474` is the candidate map request (also `0x14c4` → `0x00404078` and `0x14c6` → `0x00403fa4`). (1) read the three handlers far enough to write the request body (mesh, level, parcel, reply task); (2) deliver one request for the parcel of M9.13's changed slot (`B48R058R`, directory `0xa10b100`, slots 17/18) on the factory card and on the card with the generated tile; (3) record which read asks for the record block (`0xa1b0a00`…), which function inflates it and which functions load the inflated words; (4) `datask_l3.py diff` of the two runs, plus the M9.13 C2 control (inverted pair entry), which must now differ.
  - Hints: the renderer/router side (`0x00425f40`, `0x004266ec`; M3.27, C-4628) *sends* such requests: its `OSM_TaskSend` call is a ready example of the body. Record blocks may be read with another tag class (rows `0x09`, `0x0a`, `0x0b` of the completion table are not yet seen running).
  - Done when: one record block of the factory tile is read and parsed in the run; the same request on the generated tile gives a named verdict; the C2 control differs; EXP + claims; `reader-coverage.md` row 17 updated.
  - Stop: if the request needs state the run cannot provide after M9.52, record the faulting read/branch and stop.
  - Falsifier: the firmware reads the record block but no function loads the inflated bytes (then the consumer is another task: name the message that carries the buffer away).
  - Claims: C-5910–C-5919 (was none yet (take the next free block when claimed); fresh block for this run)
  - Result: `docs/experiments/EXP-2026-11-20-M9.53-record-block-read.md` (C-5910–C-5917). `datask_l3.py mount --request MESH` (new; opens the client slot with `0x003ed6e8`, which `0x00405970` requires) reads one record block after the mount: parcel code `0xa6cdd6be` (the record's own words 0–1; directory (77, −83) of `B48R058R`) → tag `0x0900`, handler `0x00404ee4` (memmove to the buffer start), word swap `0x003f6968`, inflate `0x0054233c`, unit table read by `0x00405078` (the "parsed" of Done when: read, inflated, unit table read and served; the link walk is M9.58), reply `0x14b6` sub 3 (data). On the generated tile the firmware reads **our** record (from our pair entries), inflates it to 184 B with the Adler-32 checked, reads its unit table and answers sub 3 as for the factory record; pair-entry flip (M9.13 C2) and record-byte flip are DIFFERENT (the latter: sub 9). Navigator review fixed the request id (`0x26c18ab2` got sub 9 = no record; C-5916 retracted, C-5918). Correction of M9.52: state 3 refuses map requests; they are served in state 2 (C-5913). The links are walked by the client task (`0x14b6` sub 3): M9.58.

- [x] **M9.58 — Walk our road record in the client task: hand `0x14b6` sub 3 to the renderer**
  - Status: done · Owner: task/m9.58-renderer-walk-record · Critical: yes · Pair: required
  - Step: P1
  - Depends: M9.53 (done)
  - Goal: M9.53 makes the data-access task read and inflate our record and serve it (`0x00405078` reads the unit table, reply `0x14b6` sub 3; C-5918); the links are walked by the client task that gets that reply. Rule 13 for records: see the firmware walk *our* links.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --position 51.70,17.45 --request 0xa6cdd6be` prints `reply 0x14b6 sub 3: 0x1 0x4 0xd8b53c 0x0 0x0`; M4.40's `tools/datask_req_l3.py` covers the same request path (C-5920–C-5927).
  - Scope: EU2011. (1) find the task that sends `0x14b5` with kind 4 (renderer, C-5641/C-4628: `0x00425f40`) and its handler for `0x14b6` sub 3; (2) where it finds the inflated record (the reply's `+20` pointer, the slot at `0xd98fe0`, or the copy at `0x00d53f20`); (3) run that handler in `datask_l3.py` (or a new tool next to it) and watch the inflated record; (4) F/G compare and a control that changes one link of our record (decoded with `clarion_tile`).
  - Done when: the functions that load our record's link and shape words are named with byte counts on F and G, and a one-link change gives DIFFERENT; EXP + claims; reader-coverage row 17.
  - Stop: if the handler needs the renderer's own state that cannot be set after two models, record the faulting read and stop.
  - Falsifier: the client handler copies the record but loads none of its link words (then name where it goes next).
  - Claims: C-6010–C-6019
  - Result: EXP-2026-11-21-M9.58-renderer-walk; 0x0042613c copies rec+0x2c 11264 B F / 512 B G and the tail 1112 B / 20 B; one-link change DIFFERENT; no link word loaded, next hop LOC_map (M9.66)

- [ ] **M9.56 — The router computes a route on our graph in L3 (not only reads it)**
  - Status: blocked · Owner: — · Critical: yes · Pair: required
  - Step: P2
  - Depends: M4.40 (grammar), M4.54 (reply path driven in L3, done, `tools/rgd_reply_l3.py`), M5.57 (a written section 2), M9.13 (generated tile read in L3, done)
  - Unblock: M4.40 done (M5.57 needed only for the generated half of Done when)
  - Goal: rule 13 for routing: today L3 shows the router *receives* section 2 (M4.54); nobody has seen `Navi.exe` produce a route. Run the router's search over a factory tile and over an M5.57 tile and compare the result with a route we compute ourselves on the decoded graph.
  - Precheck: `python3 tools/rgd_reply_l3.py --selftest` passes; `python3 tools/callgraph.py callers G 0x004266ec --depth 3` shows `0x00427a34` (common ancestor); the route-search entry above the reader is named in M4.40's EXP (if not, finding it is step 1, with `callgraph.py` from the route-request message).
  - Scope: a new `tools/route_l3.py` (do not edit `datask_l3.py`/`vcard_l3.py`/`rgd_reply_l3.py`): set start/goal on two nodes of one tile, feed section-2 replies through the M4.54 path, read the firmware's link list. EU2011 first; one tile, no cross-tile route. Reference: shortest path on the decoded graph (`tile_graph_roundtrip` model) with the same cost the firmware uses, or link-sequence equality only if cost is unknown (say which).
  - Input: M4.40/M4.54 EXPs, `tools/rgd_reply_l3.py`, `tools/datask_l3.py`, `tools/tile_graph_roundtrip.py`, M4.39 link key.
  - Done when: factory tile: the firmware's link sequence for one start/goal pair equals the reference; control: blocking one link (or flipping its `oneway`) in the tile changes the firmware route (or makes it fail); generated half (after M5.56): the same check on an OSM-built tile.
  - Stop: if the search needs global state the model cannot provide after two fixes (e.g. a cross-tile network level), record which state and stop; that is an M8 (L4) item.
  - Falsifier: the firmware route is unchanged when the only link between start and goal is removed.
  - Claims: C-5860–C-5869

- [x] **M9.60 — Card gate, first slice: the firmware's own mount and file sweep as `l3check --card` rows with an exit code**
  - Status: done · Owner: task/m9.60-card-gate-first-slice · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M9.13 (done), M9.14 (done), M9.52 (done)
  - Goal: M9.12 (the software gate before any car test) waits on M9.31 → M9.41 → M9.55, all for the POI row. The rows that check a whole card already run and do not need it: `vcard_l3.py boot` and `sweep` (M9.12's own note, C-4630/C-4651) and `datask_l3.py mount` + `diff` against the factory run. They are not a gate yet: `datask_l3.py mount` exits 0 on a tile the firmware fails to read (re-run 2026-11-20 on EU2011: the M5.56 padded tile cut at `0x9100` logs two extra `ErrorLogMsg` and still exits 0). Make them one command whose exit code is the verdict, so P0/P1 cards are gated at L3 now and M9.12 only adds rows later.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image CARD --position 51.70,17.45 --json F.json` ends `state 2 … reads 28` on the EU2011 factory card (SHA-256 `105e2032…76307`); `python3 tools/vcard_l3.py boot archive/head256.img --card-image CARD` prints `firmware error log calls: 0`.
  - Scope: `tools/l3check.py --card-gate --card IMG --factory IMG [--position LAT,LON]…` runs three rows and prints PASS/FAIL/NOT RUN per row (`--card-gate` added so M9.12's plain `--card/--factory` diff gate is unchanged): `boot` (mount verdict, 0 error-log calls), `sweep` (every file read back through the firmware), `mount` (no tile read with a negative status, error-log count equal to the factory run; `SAME` when the card claims to be a no-op). EU2011 build only; a US card is `NOT RUN (build)`, never PASS. No change to `targets.json` semantics; M9.31/M9.12 keep their rows.
  - Input: `tools/vcard_l3.py`, `tools/datask_l3.py` (`mount`, `diff`), `tools/l3check.py`, EXP-2026-11-20-M5.56-no-factory-container (the negative cases), M5.49's P1 card recipe.
  - Done when: on EU2011 the factory card and the P0 card (`b0faf119…`) exit 0 with three PASS rows; a card whose `B48R058R.DAT` is the M5.56 tile cut at `0x9100` exits 1 naming the read; a card with a corrupt `DRSTR001.DAT` (M9.14's case) exits 1 at `boot`; without a card image the rows are `NOT RUN` and the exit is 3. `--selftest` covers the verdict table without vendor data. `docs/format/card-ladder.md` names this command as the L3 gate of P0 and P1.
  - Stop: if `sweep` on a full card takes more than 20 minutes, gate on `boot` + `mount` and record the sweep time.
  - Falsifier: a card that fails in the factory-compared mount but passes the gate.
  - Claims: C-6720–C-6729
  - Result: EXP-2026-11-21-M9.60-card-gate-first-slice; factory/P1/P0 3/3 PASS exit 0, US NOT RUN exit 3, neg9100 exit 1 (sweep+mount name the read), negdrstr exit 1 at boot, selftest 29 checks

- [x] **M9.61 — The US build's map client on an EU card: does the firmware in Marek's unit read Poland tiles**
  - Status: done · Owner: task/m9.61-us-build-eu-card · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M1.22, M1.22b (EU→US function map, done), M9.14 (US2011 file layer in `vcard_l3.py`, done), M9.13, M9.53 (the EU2011 run to compare with, done)
  - Goal: the only hardware is a US unit and it runs the US `Navi.exe` (H51), but every map-client result (mount, directory reads, record read) is EU2011. Region is a property of the unit, not of the card (M2.7), so the Poland card will be read by US code. Run that code now, in L3: it either reads the EU card like the EU build does, or it names the first check or table that refuses a tile outside North America. This is the cheapest test of "a Poland card in Marek's car" that exists without the car.
  - Precheck: `python3 tools/vcard_l3.py boot US256 --build us2011 --card-image EUCARD` ends with `volume table: 40 directories, 285 files` and `firmware error log calls: 0` (run 2026-11-20 on US256 `70d945d8…04da` and the EU2011 card `105e2032…76307`: the volume table SHA-256 equals the EU-build run, `58835fc7…6aad0`). `python3 tools/datask_l3.py mount --help` has no `--build` (the gap).
  - Signature: the US VAs of the data-access task entry, its handler table and the client entry come from `fn_match` pairs of the EU functions `datask_l3.py` names (derived, M1.22b), each checked with `nk_decomp.py pdata` on the US image; a `TWIN`/`NOMATCH` pair is resolved by an executed call, not by address order (H114).
  - Scope: `tools/datask_l3.py` gains `--build us2011` (per-build VA table next to `build_targets.py`, M1.32); runs: (1) US build on the US card at a US position (positive control: the factory pair), (2) US build on the EU card at 51.70,17.45, (3) US build on the EU card with the M5.11 generated tile, (4) `--request` on one mesh of (2). Compare (2) with the EU-build run read for read (file, position, length; handler VAs differ by build). Not covered: the launcher's map-code check (M2.5/M2.15), routing, the renderer (M9.58).
  - Input: `tools/datask_l3.py`, `tools/vcard_l3.py` (`--build`), `tools/build_targets.py`, `docs/format/firmware.md` (US rows), US card `https://files.viaaq.eu/sd-images/LEAF_2011-2012_US.img` (SHA-256 `53342430…c5383`), EXP-2026-11-19-M3.25-tile-reader-entry, EXP-2026-11-20-M9.53-record-block-read.
  - Done when: runs (1)–(4) are in an EXP with their end state and read lists; (2) is `SAME` as the EU-build run in file/position/length, or the first differing read and the US function that decides it are named with a control that flips it; `datask_l3.py --selftest` covers the build switch; `reader-coverage.md` says for which rows the verdict now holds on US2011.
  - Stop: if fewer than 90 % of the functions the mount enters have a `UNIQUE` US pair, record the list of unpaired ones and stop (then the task is a `fn_match` task first).
  - Falsifier: the US build mounts the US card but, on the EU card, stops before the first tile read with no error-log call — then the position/mesh table, not the file layer, is market-bound.
  - Claims: C-6360–C-6369
  - Result: EXP-2026-11-21-M9.61-us-build-eu-card; 4 runs, 236/236 US pairs, 28/28-32/32 reads SAME

- [ ] **M9.62 — One L3 number: a manifest of every card-level L3 run with its pinned verdict, and one command that re-runs it**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Step: tooling
  - Depends: M9.60 (its row runner and exit codes; this task extends the row list beyond the three gate rows)
  - Goal: three tools give three L3 counts on the same commit (`ae2cb0c`, 2026-11-20): `python3 tools/l3check.py --build-corpus` prints `runnable=1/11`, `python3 tools/progress_report.py --run-tools` prints `"pass_firmware": 4`, `python3 tools/map_signals.py l3_rows` prints `l3-running 8`. The rows run in separate scripts (`ls tools/*_l3.py | wc -l` prints 16), each with its own arguments and verdict text, and nothing re-runs them together: an engine change that breaks one is found only when someone repeats that EXP (M9.36 did it by hand for 47 runs). This is the weekly/manual vendor-image regression the QA prompt asks for, for L3.
  - Precheck: the three commands above print three different counts; `python3 tools/mmain_l3.py run archive/head256.img --card-image EUCARD` prints `RESULT: PASS (6/6 cases as expected)` and `python3 tools/point_byteorder_l3.py run archive/head256.img --card-image EUCARD` prints `RESULT: PASS (9/9)` (both re-run 2026-11-20).
  - Scope: new `tools/l3_harness/runs.json` (one entry per run: reader-coverage row, tool, arguments with `{IMG}`/`{CARD}`/`{US256}` placeholders, build, expected verdict line or JSON key, source EXP and claim) and `python3 tools/l3check.py --runs [--only ROW]`, which executes the entries and prints PASS / FAIL / NOT RUN (no image) per row; exit 1 on a FAIL, 3 when nothing ran. `map_signals.py l3_rows` and `progress_report.py` read the manifest's row list, so the three counts are one. Local or weekly only — never in PR CI (vendor images). Not covered: new L3 runs; the `runner.py` targets keep their own `--build-corpus` path.
  - Input: `docs/research/reader-coverage.md` (the eight `l3-running` rows and their EXPs), `tools/map_signals.py`, `tools/progress_report.py`, EXP-2026-11-20-M9.36-rerun-probes-pysh4 (the hand-made re-run list), M9.59 (`RUNS-ELSEWHERE`).
  - Done when: `l3check.py --runs` on EU2011 (+US256 where a row needs it) prints one row per `l3-running` matrix row, all PASS, and the EXP has the wall time; a deliberately wrong expected verdict in a temp manifest gives FAIL and exit 1; without images every row is `NOT RUN` and the exit is 3; `map_signals.py l3_rows`, `progress_report.py` and the manifest agree on the count (a selftest compares them); `--selftest` runs without vendor data.
  - Stop: if a row cannot be reduced to one command with a stable verdict line, list it as `MANUAL` with its EXP and count it separately — never as PASS.
  - Falsifier: a `l3-running` matrix row with no manifest entry after this task.
  - Claims: C-6370–C-6379

- [ ] **M9.63 — US-build map client on an EU card: record what already runs at L3, so M9.61 is one small PR**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M1.22b (EU→US function map, done), M9.14 (US2011 file layer, done), M9.53 (EU2011 record read, done). **Does not wait on M9.61** (it is its first slice); M9.61 then keeps the remaining layers.
  - Goal: M9.61 is the cheapest software answer to "does Marek's US unit read a Poland card" but it is one `Pair: required` session covering four runs and a `--build` flag on `datask_l3.py`. Half of that surface already runs on `main` under the US build — `vcard_l3.py boot US256 --build us2011` (C-4651) and the US POI reader `runner.py run poi_record_decode` (M9.10) — while `datask_l3.py mount` has no `--build` at all (`python3 tools/datask_l3.py mount --help | grep -c -- --build` = 0, M9.61's own Precheck). Nobody has written down which layer of the US map client is already exercised and on what input, so M9.61 starts by rediscovering it and its Done-when mixes layers that are already green with one that is not. Record that boundary once, with a run per layer.
  - Precheck: `python3 tools/vcard_l3.py boot archive/us256.img --build us2011 --card-image <EU card>` ends `firmware error log calls: 0`; `python3 tools/poi_position_l3.py run archive/head256.img --dir <EU REFER001> --file POINT010` ends `RESULT: ACCEPT` (the EU control for the position arithmetic, M3.34); `python3 tools/datask_l3.py mount --help | grep -c -- --build` prints `0`.
  - Scope: survey + one run per US-runnable layer, EU2011 `Navi.exe` = control, US2011 = the subject: (a) file layer: `vcard_l3.py boot`/`sweep` US build on the US card and on the EU card; (b) POI record: `runner.py run poi_record_decode` on `archive/us256.img` with `--expect-name` (the M9.10 path); (c) the tile mount (`datask_l3.py mount --build us2011`) — expected **NOT RUNNABLE** today and that is the finding, not a failure; (d) the section-2/record-block path (M9.58/M9.53) — same expectation. Record per layer: tool, input, exit code, verdict, and the missing entry point by name. No new firmware search; no `--build` implementation (that is M9.61's own Scope).
  - Input: `tools/vcard_l3.py` (`--build`, M9.14), `tools/l3_harness/runner.py` (`poi_record_decode`, M9.10), `tools/datask_l3.py` (no `--build`), `tools/poi_position_l3.py` (M3.34), US256 `70d945d8…04da`, EU card `105e2032…76307`, EXP-2026-11-19-M3.25-tile-reader-entry, EXP-2026-11-20-M9.53-record-block-read.
  - Done when: an EXP has a four-row table `layer / tool / US2011 input / verdict / missing entry point`, every RUNNABLE row has a positive control on the EU build and one negative control (wrong build or wrong card) recorded, the `(c)` and `(d)` rows are `NOT RUNNABLE` with the exact absent flag/VA named, and `reader-coverage.md` gains one sentence per layer saying whether its current verdict holds on US2011. M9.61's Scope is then edited (by its owner) to drop the layers this row proves green.
  - Stop: one session; if a US layer needs a VA that `fn_match` has no `UNIQUE` pair for, name it and leave it `NOT RUNNABLE (no pair)` — that is a result for M9.61.
  - Falsifier: a layer this EXP marks `NOT RUNNABLE` that turns out to have a runnable tool on `main` (M9.61 is then smaller than believed), or a `RUNNABLE` row whose US run disagrees with its EU control (then the layer is the answer, not M9.61).
  - Claims: C-6600–C-6609

- [ ] **M9.64 — `main_watch` counts a green `L1/L2 synthetic fixtures` run as shadowing a red gate run: the two workflows test different things**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (H117 built the watchdog; this narrows its "later green" rule)
  - Goal: `.github/workflows/main-watch.yml` triggers on `workflow_run` for **both** `"CI quality gate"` and `"L1/L2 synthetic fixtures"`, but the verdict step runs `main_watch.py --branch main --workflow "CI quality gate" --limit 40`. `classify()` marks a red gate run `shadowed` whenever **any** later run in the fetched list is green — and the list it fetches is only the gate workflow, but the "shadowed" idea assumes a later green on the same workflow proves the red is stale. QA cycle 20 saw the effect on the reverse side: `44881534307` (gate, `3e41dc89`, `todo: PO 22nd pass`) is `cancelled`, and 9 cancelled runs sit in the 40-run window with only 5 shadowed reds; the two workflows are counted as if interchangeable. A red **gate** run must be covered by a later green **gate** run to be `shadowed`; a green L1/L2 run proves nothing about selftest/claims_check/todo_check. Today's tip is green so this changes no verdict, but the rule is wrong and would hide a red the day a L1/L2-only green lands after it.
  - Precheck: `grep -n 'workflow' .github/scripts/main_watch.py` shows one `--workflow` value and no cross-workflow guard in `classify()`; `python3 .github/scripts/main_watch.py --branch main` prints `0 salient, 5 shadowed, 9 cancelled, 40 runs`; `.github/workflows/main-watch.yml` `on.workflow_run.workflows` lists both workflows but the run step passes only one.
  - Scope: `.github/scripts/main_watch.py` `classify()` (a `shadowing` run must match the red run's `workflowName`; a green from another workflow is counted as `unrelated-green` and never shadowing) and `.github/workflows/main-watch.yml` (either run the sweep once per workflow with its own `--workflow`, or fetch both and pass the workflow name into `classify`). Keep the `--selftest` and `--replay` contract; add a fixture pair (gate red then L1/L2 green → still salient). Exclusion: no change to what counts as red (`failure`/`timed_out`/`startup_failure`), no new issue marker.
  - Input: `.github/scripts/main_watch.py` (`classify`, `Verdict`, `--selftest` fixtures, `EXP-2026-11-20-H117-main-shadow-run`), `.github/workflows/main-watch.yml`, `.github/workflows/README.md` §main-watch.
  - Hints: "later" must be by `createdAt` **within one workflow**; a `cancelled` run in either workflow never shadows (the H117 rule already says so) — extend that to the cross-workflow case. Do not silently drop the L1/L2 trigger: it is useful for a watchdog on L1/L2 reds, so give it its own verdict line rather than deleting it.
  - Done when: `python3 .github/scripts/main_watch.py --selftest` passes a new case `gate-red then l1l2-green → 1 salient` and keeps `gate-red then gate-green → 0 salient`; `--replay` on a saved two-workflow run list gives the same; on today's `main` the printed counts still say `0 salient` (the tip is green) and the shadowed set is unchanged or explained; `tools/gate.py` 4 pass / 0 fail / 0 skip.
  - Stop: if `gh run list --workflow` cannot return both workflows' `workflowName` in one call, fetch per workflow and merge by `createdAt`, recording the API shape in the EXP.
  - Falsifier: a red gate run reported `shadowed` whose only later green is a non-gate workflow.
  - Claims: C-6690–C-6699
  - Step: tooling

- [ ] **M9.65 — L3 harness: run `STDDLL` exports for `Navi.exe` import thunks (unblocks M4.55)**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: tooling
  - Depends: M9.24 (import binding), M9.44 (`vcard_l3.py` import dispatch)
  - Goal: `vcard_l3.py` binds every import slot, but a `Navi.exe` thunk that tail-jumps into a **second module** (`STDDLL.dll`) has no model, so a run that calls `STDDLL!STD_MeshPnt_isValid` stops `Blocked: missing import model` even though the export exists and runs elsewhere. Teach the harness to execute the real `STDDLL.dll` export (M3.34's loader `tools/poi_position_l3.py` already maps `STDDLL` and calls `STD_MeshPnt_chgMapPnt`/`isValid`/`chgLv`), so the `Navi.exe` consumer runs through the thunk instead of faulting.
  - Precheck: `python3 docs/experiments/m4.55-repro.py` prints `consumer fault: Blocked: missing import model: STDDLL!STD_MeshPnt_isValid (called from 0x003367c2)` and `unit0 reads: 0`; `python3 -c "import sys;sys.path.insert(0,'tools');import vcard_l3 as V;print(len(V.MODELS),[k for k in V.MODELS if 'Mesh' in k])"` prints `81 []`.
  - Scope: `tools/vcard_l3.py` import dispatch (a model that maps the thunk's IAT cell `0x0055da88` → `STDDLL.dll` export RVA and calls the loaded STDDLL text at that VA, sharing `vcard_l3`'s heap/memory map); the `STDDLL` mesh exports at minimum `STD_MeshPnt_isValid`, `STD_MeshPnt_chgLv`, `STD_MeshID_judgeLevel`, `STD_MeshPnt_initPrm`, `STD_MeshPnt_chgMapPnt`. EU2011 build A only. No host stub that fakes a return value; no new reader logic.
  - Input: EXP-2026-11-21-M4.55-rpf-consumer-import-block (the call chain and the stop), `tools/poi_position_l3.py` (the `STDDLL` loader to reuse), `tools/vcard_l3.py` (`_make_import`, `MODELS`, `Client`), `tools/cerom.py` (`exports`) for the thunk→export map.
  - Done when: `python3 docs/experiments/m4.55-repro.py` no longer faults at `0x003367c2` (the run passes the thunk and reaches the consumer's first unit-0 read), and a positive control shows the `STD_MeshPnt_isValid` model returns the same verdict as `poi_position_l3.py` on 3 records; `vcard_l3.py --selftest` covers the new binding without vendor data. Then M4.55 returns to `open` (rule 15) and its `Unblock:` clears.
  - Stop: if loading a second module's text into `vcard_l3`'s engine needs more than wiring the existing loader (e.g. a shared global map it cannot provide), record what is missing and set `blocked` on the engine change it needs.
  - Falsifier: after binding, the consumer still faults before its first unit-0 read, or the `STDDLL` call returns a different verdict than `poi_position_l3.py`.
  - Claims: C-6740–C-6749

- [x] **M9.66 — Drive the `LOC_map`/`LOC_db`/`raw_rec` tasks and find the shape walk of a served record**
  - Status: done · Owner: task/m9.66-loc-tasks-shape-walk · Critical: yes · Pair: required
  - Step: P1
  - Depends: M9.58 (done)
  - Goal: M9.58 shows the client task's sub-3 handler `0x0042613c` copies the record into the group buffers and then posts `LOC_map` a `0x0fa0` sub `0x019a` message (`0x004259bc` -> `0x0041ee14`, destination `*0x011fff74`), but no code in that run reads the copies and the `LOC_map` receiver `0x00421548` returns without touching them (C-6016, C-6017). The shape/link walk of a served record is therefore in one of the tasks the launcher `Navi_ctrl` starts (`LOC_db`, `LOC_map`, `RAW_rec`) or behind `0x00421548`'s branches that need that task's own state. Find it and run it on our record (rule 13: `docs/format/map-tiles.md` needs the walk, not only the copy).
  - Precheck: `python3 /home/marek/projekty/leafre-work/scratch/m9.58/probe_exp_record4.py` prints `[G] memmove … n=512 sha1=6ffb5d4ffbb3c3ec…` and `buffer guest reads during 0x00428200: b0=0 b1=0`; `python3 tools/datask_l3.py mount archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img --position 51.70,17.45 --request 0xa6cdd6be` prints `reply 0x14b6 sub 3: 0x1 0x4 0xd8b53c 0x0 0x0`.
  - Scope: EU2011. (1) the launcher's `Navi_ctrl` section `0x0032efa8`: how `LOC_db` (`0x111c0`), `LOC_map` (`0x111c8`) and `RAW_rec` (`0x111d0`) are started (`0x004b9174` receive loop, task create `0x0042??`), their ids landing in `0x011fff5c`/`0x011fff74`; (2) start them in `vcard_l3.py`/`datask_l3.py` (or a new tool) in the order the launcher does and deliver the `0x0fa0` sub `0x019a` message; (3) name the function that reads the group's shape buffer (`group+0x1a0`) or the tail (`group+0x1b0`) and the byte counts it loads; (4) F/G compare plus a one-link change control; (5) the other `0x0fa0` subtypes (`0x019a`, `0x0258`, M3.6's type table) if the walk is behind one of them.
  - Input: `tools/vcard_l3.py`, `tools/datask_l3.py`, `tools/sh4dis.py`, `tools/sh4xref.py`, EXP-2026-11-21-M9.58-renderer-walk (C-6010–C-6017), EXP-2026-11-06-M3.6-tile-sections-renderer (`0x0fa0` type table), `docs/format/map-tiles.md`.
  - Done when: the function(s) that walk a served record's shape/link words are named with their VAs, the byte counts they load on F and on G, and a one-link change gives DIFFERENT; or the walk is shown to need the display/preview layer and the task records where it stops, with the positive control that the same harness runs one other `0x0fa0` subtype end to end. EXP + claims; `reader-coverage.md` row 17.
  - Stop: if a task needs the display driver (`XGLDLL`/`MDP_draw`) to be mapped, record the missing export and stop; do not stub the draw.
  - Falsifier: the served record's link words are never loaded by any code, and the shape buffers are dead until the next map request overwrites them.
  - Claims: C-6770–C-6779
  - Result: the shape walk is `fn 0x0041f3dc` (EU2011 build A) in `LOC_map`, reached through `fn 0x00421548`; new `tools/locmap_l3.py` runs the firmware's own chain (position message -> requester `fn 0x00425f40` -> data-access read -> `fn 0x0042613c` copy -> `LOC_map`). Loads: F 5,363 (10,726 B, 6,868 distinct), G 49 (98 B, 70 distinct); tail buffer 0. G's reference word (record word 58 = `0x0100`) points past the record; one changed reference word gives DIFFERENT on F and G; M9.58's word 59 is not read; G's shapes are counted 0 in the result table. No display code needed. EXP-2026-11-21-M9.66-loc-map-shape-walk, C-6770–C-6779; follow-ups M9.67, M5.72

- [ ] **M9.67 — Host model of the `LOC_map` shape walk `fn 0x0041f3dc`, checked against the firmware trace**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Step: P1
  - Depends: M9.66 (done)
  - Goal: M9.66 runs the firmware's own chain (position -> request -> record -> `LOC_map`) and shows `fn 0x0041f3dc` walks the shape words: rows, shape header, points with flag-dependent extra words, one reference word per point (C-6774, C-6775). It counts shapes of the factory record into the result table `*0x00e8f5dc` and counts nothing for our generated record (C-6778). Write the walk as a host function (rule 13: the writer needs the reader's rules) and find the rule that leaves a generated shape uncounted.
  - Precheck: `python3 tools/locmap_l3.py run archive/head256.img --card-image archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` prints `shape-buffer loads: 5363 (10726 B), 6868 distinct bytes` and `RESULT: walk ran`.
  - Scope: EU2011. (1) decode `fn 0x0041f3dc` (0x11dc bytes) and `fn 0x0041f04c`/`fn 0x0041f26c` into a host model that predicts, for a shape buffer, the ordered list of loaded offsets and the four result entries; (2) check it against `locmap_l3.py` (`first_reads`, `trace_sha1`, `result_table`; add a full-trace dump if needed) on F, on G and on at least 20 other kind-4 records of `B48R058R` (other meshes: change `--mesh`); (3) name the condition that gives G zero counts and one record edit (`--patch`) that makes a count non-zero; (4) the divided-record branch `fn 0x004205b8` if a record with DIVID other than `0x0303` can be served.
  - Input: `tools/locmap_l3.py`, EXP-2026-11-21-M9.66-loc-map-shape-walk (C-6770–C-6779), `tools/sh4dis.py`, `tools/ze0-viewer/tools_ze0/fa_encode.py`, `docs/format/map-tiles.md`.
  - Done when: the host model reproduces trace and result table of the firmware on F, G and 20 more records (equal SHA-1), the zero-count cause on G is named with a patch control that turns it non-zero, and `docs/format/map-tiles.md` states the shape layout the walk requires. EXP + claims; `reader-coverage.md` row 17.
  - Stop: if another mesh needs `STDDLL!STD_MeshID_getAny` (other quadrants do, C-6779), use only meshes and positions that do not, and name M9.65 as the unblock for the rest.
  - Falsifier: the model matches F but cannot match G or the other records without per-record exceptions; then the walk depends on state outside the shape buffer and the EXP must name it.
  - Claims: C-6840–C-6849

- [x] **M9.68 — Mutation sweep of the tile header at L3: which fields does the map client check**
  - Status: done · Owner: task/m9.68-tile-header-sweep · Critical: no · Pair: required
  - Step: P1
  - Depends: M3.25 (done), M9.13 (done)
  - Goal: We know a generated tile 'reads the same as factory' and a fresh-container tile fails (M9.52/M9.53). Map the acceptance envelope: flip each header and table field of a factory tile in turn and record whether the mount/read path still completes.
  - Precheck: `python3 tools/datask_l3.py mount archive/head256.img --card-image CARD --position 51.70,17.45` completes on the factory card (the recipe in project notes and M9.13).
  - Scope: EU2011, one tile, the 512-byte common header and the level/box tables: one mutation per field (not per byte), verdict read-same / read-different / rejected, with the rejecting `fn`.
  - Input: `tools/datask_l3.py`, `tools/tile_drop_l3.py`, `tools/validate_mutation.py`, `tools/ze0_tile_header.py`, `docs/format/map-tiles.md`.
  - Done when: new `tools/tile_sweep_l3.py` (`--selftest`; `sweep` prints the table) and an EXP table field → verdict → `fn`; fields the client checks are marked in `docs/format/map-tiles.md`.
  - Stop: one session; at most 64 mutations.
  - Falsifier: no mutation is ever rejected (then the path under test does not parse the header and the sweep needs the next stage).
  - Claims: C-8000–C-8009
  - Result: EXP-2026-11-22-M9.68-tile-header-sweep; 52 fields: read-same 33 / read-different 18 / rejected 1 (fn 0x0040acb8); C-8000-C-8009; gate 5 pass 0 fail 0 skip

- [x] **M9.69 — One trace format for L3 and L4 reader calls**
  - Status: done · Owner: task/m9.69-reader-trace · Critical: no · Pair: solo
  - Step: tooling
  - Depends: —
  - Goal: L3 tools print reader results each in their own shape, and the L4 parity task (M8.H11) will add another. Define one JSON record (build, function, arguments, reads, result) so comparisons and the manifest of M9.62 are mechanical.
  - Precheck: `python3 tools/l3check.py --help` works; `ls tools/*_l3.py | wc -l` shows how many producers exist.
  - Scope: a schema (`tools/reader_trace.py` with `--selftest` and `validate FILE`), an adapter for two existing L3 tools (`mmain_l3`, `drstr_l3`), documentation in `docs/research/feedback-loop.md`. No change to verdict logic.
  - Input: `tools/mmain_l3.py`, `tools/drstr_l3.py`, `tools/l3check.py`, `tools/progress_schema.py`.
  - Done when: both adapted tools write traces that `python3 tools/reader_trace.py validate` accepts; their existing selftests and `tools/l3check.py` verdicts are unchanged (command output before/after in the EXP).
  - Stop: one session.
  - Falsifier: a field needed to compare two runs is missing from the schema for one of the two tools.
  - Claims: C-8010–C-8019
  - Result: EXP-2026-11-22-M9.69-reader-trace; C-8010–C-8013; reader_trace selftest 54/54, both adapted tools validate (6+1+9 records), selftests and l3check unchanged (pass=3 fail=0 runnable=3/13)

- [x] **M9.70 — A Polish POI name through the firmware: `Łódź Żabieniec` at L3**
  - Status: done · Owner: task/m9.70-polish-poi · Critical: no · Pair: solo
  - Step: P4
  - Depends: M9.10 (done)
  - Goal: M9.10 showed the firmware returning a renamed POI. Repeat with a name using Polish letters, stored as M4.13 says, and see what the firmware's name accessor returns byte for byte.
  - Precheck: `python3 tools/point_walk_l3.py --help` and `python3 tools/mutate_refer_poi.py --help` work; the M9.10 EXP names the commands.
  - Scope: EU2011: rename one POI to a string with ł, ó, ź, Ż; run the walker and the name accessor; compare returned bytes with the stored ones.
  - Input: `tools/mutate_refer_poi.py`, `tools/point_walk_l3.py`, `tools/point_name_accessor.py`, the M9.10 EXP.
  - Done when: the L3 run returns the name with every letter intact (bytes quoted as hex of the non-ASCII letters only), or the EXP names the letter and the function that changes it.
  - Stop: one session.
  - Falsifier: the returned name equals the stored one only for the ASCII part.
  - Claims: C-8020–C-8029
  - Result: EXP-2026-11-22-M9.70-polish-poi-l3; record 0 a3f3bcaf and record 1 b3f3bcaf returned byte-identical; walker 8/8, accessor 1000/1000, gate 5 pass/0 fail/0 skip

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