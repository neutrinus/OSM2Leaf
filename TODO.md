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
| `US256` (US firmware head, 256 MiB) | `head -c 268435456 PATH_TO_US` until H62 adds `--image US256` | `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da` |
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

## Priorities (PO grooming 2026-11-19, 17th pass; retro 2026-11-18-3, SE `81da684`)

**This cycle moved the card ladder, not the two reader numbers.** Cycle 14
closed eight tasks (P0 deepened: M5.44 level 2, M5.45 idempotence, M5.46 the
P1 census); readers stay **6/30** and L3 **1/30**; said first, per rule 17.

**The four rule-17 map numbers — run each, do not retype** (snapshot
2026-11-19T13:30Z, `origin/main` `dea3e56`):

```bash
# M1 reader rows with a located reader (6) — partial/access-path rows counted apart (5)
python3 -c "import sys,pathlib;sys.path[:0]=['tools'];from progress_report import parse_reader_coverage as p;d,_=p(pathlib.Path('docs/research/reader-coverage.md'));s=d['summary']['firmware_reader'];print('located',s['located'],'partial',s['partial'],'unlocated',s['unlocated'])"
# M2 reader rows with a running (non-BLOCKED) L3 target result (1 — row 6, cmp_ind_reader)
grep -E '^\| [0-9]+ \|' docs/research/reader-coverage.md | awk -F'|' '{gsub(/ /,"",$9); if ($9 ~ /PASS|REJECT/) c++} END{print "l3-running", c+0}'
# M3 factory-tile nonzero bytes inside container structures (directory+slot spans), per tile
python3 -c "import sys;sys.path[:0]=['tools/ze0-viewer/tools_ze0'];import clarion_tile as c
for n in ['B28R070R','B30R048R','B48R058R']:
 d=open('/home/marek/projekty/leafre-work/m5.4/card-factory/MAPAL001/%s.DAT'%n,'rb').read();t=c.read_tile(d);iv=[]
 for s in t['sections']:
  for L in s['levels']:
   for D in L['dirs']: iv.append((D['off'],D['end']));iv+=[(x['block_off'],x['block_end']) for x in D['slots'].values()]
 iv.sort();m=[]
 for a,b in iv:
  if m and a<=m[-1][1]:m[-1]=(m[-1][0],max(m[-1][1],b))
  else:m.append((a,b))
 nza=sum(1 for x in d[0x1000:] if x);nzc=sum(sum(1 for x in d[a:b] if x) for a,b in m)
 print(n,'%.2f%%'%(100*nzc/nza))"
# M4 highest card-ladder step whose own gate passes (P0 — M5.34 factory-backed run)
python3 -c "import json;r=json.load(open('/home/marek/projekty/leafre-work/m5.34/report.json'));print('P0' if r['cardcheck_ok'] and r['l2check_ok'] else 'none')"
# P1 census (M5.46): how many tiles the test region is contained in
python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json /home/marek/projekty/leafre-work/m5.29-factory-root/MAPAL001 | tail -1
```

Numbers now (quoted from those commands, this host): **readers 6/30 located**
(+5 partial), **L3 running 1/30**, **factory tile nonzero bytes inside
structure unchanged** (B28R070R 99.98 %, B30R048R 95.86 %, B48R058R 76.28 %),
**highest step P0**, **P1 census: `contained=1 intersects=0 outside=62`** —
all of Dolnośląskie's 14.0–17.9 E × 49.9–51.9 N box is inside one tile
(`B48R058R`), so P1 is one factory tile copied verbatim and the all-tile run
is not a stitching problem.

*How it went since 2026-11-18.* Cycle 14 merged nine tasks (M5.43, M3.26,
M9.42, M5.44, M5.45, M5.46, M9.43, H91 done; H92 blocked on H111) in two
rule-17 batches, with no record-repair task. The two ghosts (M5.46, M9.43)
were status lines a squash merge left at `in progress`; the SM pass fixed
them. **Claim collisions** cost three renumber rounds — PR #229's reservation
is the process fix.

**Directions without hardware, in order:**
1. **P0 → P1 on the card.** **M5.47** (fit census: does one changed tile fit
   its FAT chain) → **M5.30** (1:1 diff card, the last P0 step) → **M5.48**
   (a refused run must not leave a card-looking tree) → **M5.41** (one
   expected-change-set). Then **P1**: copy the one contained tile verbatim
   (M5.46 says it fits) and record the display-only gate — no block yet.
2. **Firmware as the format specification.** **M3.27** (tile-reader entry
   arguments, static) → **M3.25** (the L3 run it enables) → **M4.40**
   (section 2/router) → **M3.23**+**M9.38** (REFER families).
3. **Emulation as the unit.** **M9.36**/**M9.37** → **M9.44** → **H111**
   (the gate wiring; H92 waits on it). M8.E4 (full `Navi.exe`) after those.
4. **Data against data.** **M4.41** (2011/2014/2016 differential) and
   **M4.2**/**M5.36** (OSM ground truth) decode fields with no firmware.

**Next for the TL (map tasks only; rule 17):** **M5.47**, **M5.30**,
**M5.41**, **M3.27**, **M9.36**, **M5.48**, **M9.41**, **M4.40**, **M3.25**,
**M9.37**.

### Critical path to "maps run in the car" (L1 → L2 → L3 → L4 → L5)

> Level mapping (2026-11-09): **L3** = firmware fragments, **L4** = full-system emulator (QEMU/M8), **L5** = bench/car (M6).

- **L1 (cheap, ready):** `cardcheck --image` + `imgpatch`/manifest diff. Blocking: **H40** (vendor-free in-process fixture) → **H41**/**H42** (per-feature matrix). The card path itself waits on L2's **M5.30**. H40 starts from **H103** (a tree `cardcheck` accepts) + **H105** (a broken one that must fail) and is pinned by **H104** (baseline).
- **L2 (necessary — rule 13): — THIS IS THE CRITICAL PATH.** **M5.34** done, M5.44 (level 2) and M5.45 (idempotence) done → **M5.47** (fit census) → **M5.30** (1:1 diff card, P0 complete) → **M5.11** (OSM→card end to end) → **M5.35** (one command + evidence bundle) → **M7.1** (all Dolnośląskie). **P1 = M5.46** done (contained=1: one factory tile, no stitching) then the all-tile copy step (no block yet). Feature gaps: **M5.16** (routing graph), **M5.36** (road-class golden), **M5.37** (route-graph golden), **M4.36** (names, blocked on **M3.13**); support **M5.3**, **M5.23**, **M5.33**, **M5.32**, **M5.41**, **M5.43**, **M5.38** (ladder page).
- **L0/L4 readiness (QA 2026-11-18):** the first L4 row is not a run but the **H110** panel (`l4_status.py`, F0–F4, `NOT RUN` without a log); the L2→L3 link is **H106** (the corpus names M5.34's tile) and **H107** (the blocked split).
- **L3 (virtual; SKIP/BLOCKED never PASS):** **M9.41** (register the US POI walk row) → **M9.31** (no-diff verdicts) → **M9.12** (`l3check --card`). The **tile** reader — the file L2 writes — has no runnable target: **M3.27** (entry arguments, static) → **M3.25** (the run) → **M9.13**; names need **M3.11c**; discovery **M3.23**/**M3.24** → **M9.38**; **M1.19** for `INIT` bytes. QA 2026-11-18: the corpus does not name M5.34's tile (**H106**) and the `blocked=6` number hides two argument-only rows (**H107**).
- **L4 (QEMU/M8):** **M8.A2** is `done` (QEMU 8.2.10 `-M ze0`, one run, exceptions 0). Next: **M8.A3**/**M8.A6** → **M8.E4** (full `Navi.exe` on a generated card); **M5.43** repairs the `--check-version` exit code the next bump needs. **M1.19** gates any `INIT`-byte run. The row itself is prose until **H110** (readiness panel + `l4_status.py`).
- **L5 (bench/car, one variable):** never skip S0. **M6.2** S0 (Marek/non-Claude) → **M6.5** S1 → **M6.6** S2 → **M6.7** S3; prep **M6.13**, **H29**. Hardware unavailable; `l3_precond.py` before every bench card.

**Next 5 for the TL (one per cycle is enough; all deps done):**
1. **M5.30** (L2) — the 1:1 diff card; the last P0 step and the first card that differs from factory in known clusters. It is marked `Critical: no`; the PO recommends the TL raise it, because every later rung rests on it.
2. **M5.44** (Critical, L2) — level-2 detail; settles the `parcel_geo` vs `directory_bbox` 4× grid before a wrong-geometry splice passes every L2 check.
3. **M9.41** (Critical, L3) — register the running US POI walk as an S1 evidence row (`M9.31`→`M9.12` next); cheapest turn of L3 prose into a gate.
4. **M3.25** (Critical, L3) — the tile/route reader VAs; without it L3 never sees a `MAPAL001` file.
5. **M5.41** (L2) — one expected-change-set; a correct run that `expected` calls wrong is a card-gate defect waiting for M5.30.

**Batch, not per-cycle (record repair — real, off the critical path):**
**H91**+**H92**, **H93**+**H94**, **M1.32**, **M1.33**, **H99**, **H100**,
**M9.42**/**M9.43** (with **M9.41**), **M5.42** (cheap solo). One TL pass
closes them; the retro (action 1) sets the bar at ≥ 7 IDs.

**First slice (rule 17 "big tasks are split"):** P1 (all Dolnośląskie tiles,
display-only) had no block; **M5.46** is its first slice (the profile→tile
containment census, no write). Take it with or just after **M5.30**.

**Archive: 2 moved** (`H79`, `H80` → `docs/research/todo-history-2026-11-18.md`).
TODO.md **3923 → 3930** lines (before/after this pass: −24 for the two
archived blocks, +31 for this section and **M5.46**; the 1500 line rule stays
unmet by design — 61 done blocks are cited by live tasks). Earlier passes:
`docs/research/todo-history-2026-11-05.md`, `-06.md`, `-09.md`, `-13.md`,
`-15.md`, `-16.md`, `-17.md`, `-18.md`.

### Map signal (read first)

Board: **130 open / 61 done / 24 blocked** (215 blocks; parsed 2026-11-18 after
this pass), 0 `in progress`, 0 ghost claims, `gate: 4 pass`. **34 of 47 H blocks
are open**; 13 blocks exist only to repair a record or the gate that missed it.
The map moved one step in two cycles
(P0 via M5.34); readers 6/30 and L3 1/30 did not move. A cycle that moves none
of the four numbers above says so in its first line.

---

## H — Housekeeping

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

- [ ] **M1.4 — Extract compressed `FILESentry` payloads**
  - Tool: `cerom.py files --extract --decompress` writes stored bytes,
    classifies OK/UNSUPPORTED/FAIL and never writes a wrong-length decode
    (EXP-55, C-573); EXP-51 says the real payload is not a stdlib format.
  - Status: blocked · Owner: task/m1.4-extract-filesentry-payloads · Critical: no
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
  - Claims: C-680–C-683

- [x] **M1.2e — Try public CE ROM decoders on the two EXP-49 sections**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (needs GitHub/source downloads, rule 12)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
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
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-2070–C-2079

- [ ] **M1.2f — Port the nk.exe block codec (`DECOMP_BLK`) to pure Python**
  - Status: blocked · Owner: task/m1.2f-decomp-blk-python · Critical: no
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


- [x] **M1.2g — `decomp_oracle.py` fragment API + CE XIP LZXD reference vector harness (unblocks M1.2f verification)**
  - Status: done · Owner: — · Critical: no
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M1.2f (framing/tree landed), M8.E1b (VAs)
  - Goal: give M1.2f a verifiable oracle/reference path without guessing 245/245: a harness feeds block/section fragments and compares decoded bytes/hash to a trusted reference (QEMU/runtime oracle when available, or a pinned CE XIP LZXD reference output with licence/URL/SHA-256), proving the bitstream/tree variant.
  - Precheck: `python3 tools/cedecomp.py --selftest` passes; EXP-49 vectors and M8.E1b VAs recorded; `python3 tools/decomp_oracle.py --selftest` passes (contract implemented: `osm2leaf.decomp_oracle/v1`, pinned EXP-49 lengths/targets, `vectors --json`, `verify`; extend with `source`/`entry_va`/`input_hash` when wiring M8.E1c/M9.29 runtime output).
  - Scope: `tools/decomp_oracle.py` (stdlib, `--selftest`) schema/result verification for EXP-49/fragment mode + optional wiring to M8.E1c/M9.29 runtime output. No 245/245 claim; no vendor bytes committed.
  - Input: M1.2f `XipLzxd` framing, EXP-49, M8.E1b `DECOMP_SECT/BLK`, M8.E1c/M9.29 JSON when available; external reference requires recorded licence/URL/SHA-256 (non-Claude if download needed).
  - Done when: schema documented and `--selftest` has synthetic controls; EXP-49 sec1/sec2 reports `PASS` only with a trusted decoded reference hash, else `FAIL`/`NO_ORACLE` (never silent pass). M1.2f/M9.29/M9.30 consume the schema; at least one runtime or pinned-reference result is recorded in an EXP.
  - Stop: if no trusted reference obtainable (no QEMU, no licensed reference output), keep EXP-49 `NO_ORACLE` with blocker named and land/keep schema + synthetic selftest.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
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

- [ ] **H53 — make the documented `--strict` mode honest: it is implemented but the board is not clean (69 errors)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (this task is the board cleanup; it is what H53's own Stop anticipated)
  - Goal: H53's original premise ("`main()` does not define the flag; `--strict` is an argparse error") is stale. The flag exists (commit `9733980`) and is wired: `python3 tools/todo_check.py --strict` exits 1 with 69 `ERROR` lines over 25 firmware/search tasks (3 missing fields each), while the default run exits 0 with those same lines as `WARN`. The gap is therefore not a missing flag but a board that has never satisfied rule 14: 25 firmware/search tasks (open, blocked or already `done`) lack `Precheck`/`Scope`/`Stop`; 11 of them are `Critical: yes`. `TODO.md:248` still lists H53 as a cheap fill task and Q1's "Take first" never mentions it, so nothing will close it unless a role owns it.
  - Precheck: `python3 tools/todo_check.py --strict 2>&1 | grep -cE '^  ERROR'` prints `69`; `python3 tools/todo_check.py --strict; echo $?` prints `1`; `python3 tools/todo_check.py; echo $?` prints `0` (default still green).
  - Scope: (a) `tools/todo_check.py` only if a real bug is found in the strict path (otherwise no code change); (b) `TODO.md` only: give each of the firmware/search tasks the three fields (5 of the 25 are already `done`; a `done` task missing the fields is a warning only, so decide per task whether to backfill), or mark the ones that genuinely cannot have a `Precheck` as `Status: blocked` with the reason. Do **not** silently delete tasks or relax the rule. Add the missing `Depends:` values against the merged task IDs.
  - Input: `tools/todo_check.py` (`REQUIRED`/`strict_firmware` lists, `_parse_depends`), `python3 tools/todo_check.py --strict` output (69 ERROR + the warning text that names each task), `TODO.md` sections M1/M2/M3/M8/M9.
  - Done when: `python3 tools/todo_check.py --strict` exits 0 on `main`; `python3 tools/todo_check.py` exits 0 on the same tree; `python3 tools/selftest.py --only todo_check` passes; the EXP records the before/after ERROR count and which tasks were given fields vs marked blocked.
  - Stop: if the clean board needs a decision a role cannot make (e.g. an externally blocked task whose block owner is unknown), record those tasks under `Status: blocked · Unblock: <human>` and lower the Done-when to "no ERROR for tasks this cycle can own" — never lower the rule itself.
  - Claims: C-3650–C-3659
  - Result: pending (this task is re-scoped, not done).

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

- [ ] **H97 — `l1l2_fixtures` computes `ok` without the required categories, so two NOT COVERED levels still read "OK"**
  - Status: open · Owner: — · Critical: no · Pair: required
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

- [ ] **H99 — `.github/workflows/README.md` still documents the pre-H85 hard gate (selftest + claims + todo), not `tools/gate.py`**
  - Status: open · Owner: — · Critical: no · Pair: solo
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

- [ ] **H100 — `claims.md` carries 285 `RESERVED (TASK).` placeholder rows, and no gate notices when the task is `done`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (claims_check is on `main`); the retro 2026-11-17-3 multiplicity finding
  - Goal: a 10-ID block was meant to be a reservation, but every block was also written out as ten `| C-xxxx | RESERVED (TASK). | — | — | — |` rows, and nothing ever removes them. SE 2026-11-17 counted **285 RESERVED rows over 60 tasks**: **97 rows name a `done` task** (e.g. C-4179 for the just-merged M9.39, C-4139 for H90, C-4102…C-4109 for H87), 34 name a `blocked` task, and 151 name a task no longer in TODO.md. `claims_check --strict --count-check` passes over all of them, so "reserved" reads as "registered" (the retro's exact defect) and an agent scanning for the next free claim sees a wall of dead placeholders. Make the placeholder a gate-visible state and retire the rows whose owner is `done`.
  - Precheck: `grep -c 'RESERVED (' docs/research/claims.md` prints `285`; `grep -o 'RESERVED ([A-Za-z0-9._]*)' docs/research/claims.md | sort | uniq -c | sort -rn | head` shows the per-task spread; `python3 tools/claims_check.py --strict --count-check` is OK with those rows present (the defect: no gate sees them).
  - Scope: `tools/claims_check.py` (a `--reserved` mode, on under `--strict`) that fails when a `RESERVED (<ID>).` row names a task whose `Status:` is `done` or that is absent from TODO.md, with the task ID and count in the message; and `docs/research/claims.md` — delete the RESERVED rows for `done`/absent tasks (keep the rows for `open`/`in progress` tasks, which are true reservations). Do **not** renumber any real claim ID and do not touch a task's numeric `Claims:` header. If a whole block's owner is gone but its numbers must stay scar-free, leave a single `| C-a–C-b | reserved block, owner retired |` note row rather than ten.
  - Input: `tools/claims_check.py` (`_run_counts`, `main`, the row parser), `docs/research/claims.md`, the TODO `Status:` values (`todo_check._parse_status`), the 285-row census above.
  - Hints: match the owner token exactly (`RESERVED \(([^)]+)\)`); a `done (negative …)` status still parses as `done` via `_parse_status` so H95-style blocks retire too. Keep the check additive (default off is wrong here — the retro wants it loud), but make the message list at most ten offending tasks so it stays readable. The 151 absent-task rows are the bulk; deleting them must not change `--count-check`'s mismatch count (those are not count-bearing rows).
  - Done when: `python3 tools/claims_check.py --strict` fails on today's `claims.md` with a `RESERVED row names done/absent task` list; after the cleanup it passes and `grep -c 'RESERVED (' docs/research/claims.md` counts only rows whose owner is `open`/`in progress`; a synthetic fixture with one done-owner RESERVED row fails and one open-owner row passes (`--selftest`); `python3 tools/gate.py` green; `--count-check` still `0` mismatches.
  - Stop: if deleting the absent-task rows would break a `Supersedes:`/`Superseded by:` pointer, keep those specific rows and list them as `OBSERVED retained` — never renumber a real claim.
  - Falsifier: a `RESERVED (M9.39).` row (M9.39 is `done`) still passes `--strict` after the change.
  - Claims: none until rows are committed

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

- [ ] **H58 — Make the claims ledger reject non-runnable evidence (`...`/`START`/`MODULE` placeholders, prose loops)**
  - Status: open · Owner: — · Critical: yes · Pair: solo
  - Depends: — (`tools/claims_check.py` is on `main`; no other task's block is needed)
  - Goal: the evidence column is the ledger's whole value, but `claims_check.py` only checks IDs and annotations. `C-3612`, `C-3613`, `C-3614` (M1.23) cite a "loop over `cerom.py … modules`" and `--image-start START --module MODULE` that exist only in a `/tmp` heredoc, and `C-3711` (H55) cites `cmp ...`. SE 2026-11-15 reproduced the census (A 149/87,530/20 plain, B 91/21,930/19, C 88/25,243/23) only with a throwaway script — that is exactly rule 16's defect, and it reached `VERIFIED` because no check reads the command. (C-3712 is the subtler "producer command omitted" case; a check cannot see it, so reviewers still read.)
  - Precheck: `python3 tools/claims_check.py` is OK today; `grep -n 'C-3612\|C-3613\|C-3614\|C-3711' docs/research/claims.md | grep -cE '…|\.\.\.|--image-start START|--module MODULE'` prints 3 (C-3612, C-3613, C-3711), and `C-3614`'s evidence is the bare prose "census loop over `pdata.load_table`" with no invocation at all — 4 rows fail a runnable-command rule, so the defect is present, not hypothetical.
  - Scope: `tools/claims_check.py` only: a `bad_evidence()` pass over rows whose Status starts with `VERIFIED`; fail a row when, after the EXP name, its backticked command span (a) contains `...`, `…` or an unexpanded placeholder token (`START`, `MODULE`, `VA`, `<...>`), (b) has no span starting with a known invocation (`python3`, `tools/`, `git`, `curl`, `sha256sum`, `grep`, `cmp`, `stat`), or (c) is a heredoc/`python3 -c` with no `tools/` path. Allow short hash abbreviations matching `[0-9a-f]{4,}…[0-9a-f]*`. Print one line per row and a total; land it as a warning by default and an error under `--strict` so the legacy rows do not block CI.
  - Input: `docs/research/claims.md` (all rows), `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`, `main`), `docs/experiments/TEMPLATE.md`, TODO rule 16, EXP-2026-11-15-M1.23-pdata-wireup, EXP-2026-11-15-H55-l3check-json-path.
  - Hints: do not flag English prose `…` ("switch 7…15") — require the span to open with a known invocation, so `C-207` and the hash rows stay clean. Reuse H53's `--strict` (one flag, two rules) rather than a second parser; H53 owns the board checks, this owns the ledger. Keep the duplicate/unregistered/annotation checks untouched.
  - Done when: `python3 tools/claims_check.py --selftest` passes (synthetic `cmp ...` row fails, a hash-abbreviation row passes, a prose row without a command fails, an EXP+real-command row passes); default `claims_check.py` still exits 0 on the current ledger and prints the non-runnable row count; `--strict` exits 1 and names at least `C-3612`, `C-3613`, `C-3614`, `C-3711`; `selftest.py` passes.
  - Stop: if the allowlist grows past ~20 IDs, ship the report and the count with `--strict` opt-in (default still 0) and hand enforcement to H53, recording the row count in the EXP.
  - Claims: C-3770–C-3779

- [ ] **H61 — `claims_check`: every cited EXP record must exist on `main`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/claims_check.py` is on `main`); coordinates H58 (same tool, evidence *command*; this one checks the evidence *name*)
  - Goal: `claims_check.py` verifies IDs and annotations but never resolves the EXP record a row names, so a typo'd or absent record looks registered. Today `C-1900–C-1916` cite `EXP-2026-11-08-M4.8b-poi-refs` while the repo stores `EXP-2026-11-08-M4.8b-poi-refs.tsv` (7 rows), and `C-3033` cites `EXP-…-variants.tsv` (a `.tsv`, not a record); `C-3170–C-3175` cite the `.md` suffix in prose. A row must name a file that exists, or say why it has no record.
  - Precheck: `python3 -c "import re,glob,os;m={os.path.basename(p)[:-3] for p in glob.glob('docs/experiments/EXP-*.md')};n=[l.split('|')[1].strip() for l in open('docs/research/claims.md') if l.startswith('| C-') and any(not any(p==s or s.startswith(p+'-') for s in m) for p in [x.rstrip('.,;').removesuffix('.md') for x in re.findall(r'EXP-\d{4}-\d{2}-\d{2}-[A-Za-z0-9.\-]+',l)])];print(len(n),n[:4])"` prints `8 ['C-1900', 'C-1901', 'C-1902', 'C-1903']` — the `poi-refs` rows name a `.tsv`, `C-3033` names a `.tsv` with its suffix. (A loose match that also accepts `EXP-…-<slug>.<ext>` reports 0 and hides both; the rule below must therefore require a `.md` record or an explicit `companion:` in the row.)
  - Scope: `tools/claims_check.py` only: resolve each `EXP-YYYY-MM-DD-<TASK>-<slug>` token against `docs/experiments/` by exact file name, `.md` suffix, or `<name>.<ext>` (a `.tsv`/`.json` companion next to an `EXP-…` record is allowed); report one line per unresolved row and a total; land it as a warning by default and an error under H58's `--strict`. Do not touch the duplicate/unregistered/annotation checks or H58's command-span parser.
  - Input: `docs/research/claims.md` (all rows), `docs/experiments/` listing, `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`), EXP-2026-11-08-M4.8b-poi-refs.tsv (the `.tsv`-only record the rule must allow).
  - Hints: keep the stem match (`-2`/`-3` suffixes count as the same task), resolve relative to `REPO` like `fn_audit` does, and do not grep EXP *contents* — a missing file is the defect, a missing section is a reviewer's job. Reuse H58's `--strict` rather than a second flag.
  - Done when: `python3 tools/claims_check.py --selftest` covers a row naming a missing EXP (fails), one naming a `.md` record (passes), one naming a `.tsv` next to its stem (passes) and a `-2` suffix (passes); default `claims_check.py` still exits 0 on the current ledger and prints the unresolved count; `--strict` (once H58 lands it) exits 1 and names at least `C-1900` and `C-3033`; `selftest.py` passes.
  - Stop: if H58's `--strict` has not merged, ship the warning mode plus `--selftest` and record in the EXP which rule H58 must pick up; do not fork a second ledger checker.
  - Claims: C-3810–C-3819

- [ ] **H62 — `fetch_image.py`: a `US256` head alias pinned to `70d945d8…`, so rule 11 holds for US tasks**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/fetch_image.py` is on `main`; `--part 256M` exists)
  - Goal: the EU head is a pinned first-class key (`IMG256`, `92aa525d…`), but the US head every US task needs is cited four times (`M1.22`, `M1.22b`, `M1.28` block/Result) as `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img` with the hash `70d945d8…` in prose. `fetch_image.py --image US --part 256M` verifies size only ("no SHA-256 pinned"), so a truncated/overwritten local card is not caught and no command is re-runnable from a clean checkout (rule 11).
  - Precheck: `python3 tools/fetch_image.py --image US --part 256M -o /tmp/opencode/x.img` prints `size verified; no SHA-256 pinned`; `python3 tools/fetch_image.py --image US256 -o /tmp/opencode/x.img` exits `2` `unknown image 'US256'`; `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img | sha256sum` is `70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da` and is byte-identical to `/tmp/opencode/us256.img`.
  - Scope: `tools/fetch_image.py` only: `PART_PINS[("US", "256M")] = (256 MiB, 70d945d8…)` and `ALIASES["US256"] = ("US", "256M")`; `--list` shows it; extend the `--selftest` so `resolve("US256", None)` returns the pinned hash and `resolve("US256", "1G")` exits 2. Not: changing any full-image pin, the EU head, or an EXP.
  - Input: `tools/fetch_image.py` (`IMAGES`, `PART_PINS`, `ALIASES`, `resolve`, `selftest`), the US SHA-256 above, `TODO.md` "Shared inputs" table.
  - Hints: the `IMG256` alias is the template — one `PART_PINS` entry plus one `ALIASES` line; the fixture already pins the same hash (`tools/fixtures/fn_match_eu_us_2011.json` `us_head`), so the two must agree (add a selftest check that they do, reading the fixture JSON).
  - Done when: `python3 tools/fetch_image.py --image US256 -o /tmp/opencode/us256-new.img` verifies `70d945d8…` (or `--verify` names it); `--image US --part 256M` now also verifies the hash; `python3 tools/selftest.py --only fetch_image` passes with the new cases; the `Shared inputs` table gains a `US256` row.
  - Stop: if the upstream US image is re-released (hash differs), record the new full-image hash in an EXP and pin the new head; never pin a hash you cannot reproduce from the card.
  - Claims: C-3820–C-3829

- [ ] **H63 — `fn_audit`: a `CORRECTED` verdict must name the line-specific evidence that resolved it**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (`tools/fn_audit.py`, M1.29 on `main`); coordinates H52 (edits the citations) and M1.26 (reuses the verdict)
  - Goal: `CORRECTED` is a success class, so its evidence must be visible on the row. Today an `INSIDE` becomes `CORRECTED` either because the *same line* pairs the VA with its true start or because the VA is on the static `CORRECTION_ONLY` pin; the printed row says only `CORRECTED 0x…`. The pin is a fleet-wide allowlist, so a bare `… are mid-function` line is resolved by the pin even though the line names no start. On the frozen `b56fed2` corpus the example is `TODO.md:714` (the M1.25 Goal lists the three H51 VAs as mid-function, no pair, no start): dropping the `0x00542256` pin alone turns that line's third VA into `INSIDE` — `INSIDE` 33→36, `CORRECTED` 13→10. **Post-H52 (2026-11-16) the same defect survives but smaller:** on `main` at `26f33cd` `--scope docs` is `START 229, INSIDE 0, CORRECTED 25`, and popping the same pin gives `INSIDE 5, CORRECTED 20`; the pinned VA stays `CORRECTED(pin)` on a line where the other two H51 VAs are `INSIDE` (H52 left them as historical co-citations), so the pin hides which VA the line actually resolved.
  - Precheck: on the `b56fed2` worktree (`git worktree add --detach /tmp/opencode/h63wt b56fed2`, then run `tools/fn_audit.py <abs>/archive/head256.img --scope docs --quiet` from it) the summary is `START 190, INSIDE 33, CORRECTED 13, GAP 29`; popping the `0x00542256` pin gives `INSIDE 36, CORRECTED 10`. On `main` at `26f33cd` the same command is `START 229, INSIDE 0, CORRECTED 25`; popping the pin gives `INSIDE 5, CORRECTED 20` (measured 2026-11-16) — the split must be exported on `b56fed2` as the stable corpus and only *re-measured* on `main`, never re-pinned to freeze a number. The pinned VA's line shows it as `CORRECTED` while the other H51 VAs on that line are `INSIDE` — one pin resolved a line that names no start.
  - Scope: `tools/fn_audit.py` only: a fourth label token, `CORRECTED(line)` vs `CORRECTED(pin)`, and a summary line `CORRECTED <n> (<line> line, <pin> pin)`; the pin path keeps its own selftest and `--verbose` keeps printing the allowlist. Not: changing a citation (H52), re-pinning to freeze a number, or counting the live board as if it were fixed.
  - Input: `tools/fn_audit.py` (`Verdict.label`, `_resolved`, `report`, `CORRECTION_ONLY`), EXP-2026-11-15-M1.29-fn-audit-corrections §Observations (the 13-row table and the 6+3+2+1+1 split), the `b56fed2` worktree (the only corpus whose 33/13 is stable).
  - Hints: `_resolved` already knows which branch fired — pass the branch into the verdict instead of re-deriving it in `label()`; keep `is_failure` and `--fix-list` untouched (neither may start printing a `CORRECTED` row). The number for the EXP is *which citations are pin-resolved*: run it on `b56fed2` so it does not move under later board edits. If a pin-resolved citation's own line pairs a different start, that is a second defect — report it, do not auto-fix. Each pin the EXP keeps must carry a `Pin:` line naming its independent re-check: `0x00542256` → M1.24's `--parent-of`; `0x003f5fc2`/`0x00413af4` → `pdata.py fn` at the call site. A pin with no such line is a candidate for H52 instead. Because the count moves with the board, M1.26's gate must run on a frozen corpus (a committed JSON snapshot, M1.30), never live `TODO.md`.
  - Done when: on `b56fed2` the split prints `CORRECTED 13 (<line> line, <pin> pin)` with the arithmetic in the EXP and the live tree's larger `CORRECTED` measured in the same EXP (same `INSIDE`, so the difference is only the added prose); every pin the EXP keeps has a `Pin:` line whose re-check command runs; `--selftest` proves a pair-resolved citation is labelled `line` and a pin-resolved one `pin`; with the `0x00542256` pin removed on `b56fed2` the summary reads `INSIDE 36, CORRECTED 10`; `selftest.py --only fn_audit` and `claims_check.py` pass.
  - Stop: if the split cannot be exported without changing the 13/33 counts, record the counts as an OBSERVED claim and ship only the label; do not redefine `CORRECTED`.
  - Claims: C-3830–C-3839

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

- [ ] **H65 — `progress_report`: its L4 prerequisite names an ID that is no longer a block**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/progress_report.py` is on `main`); coordinates H60 (the same live/archived/ghost distinction, for one hard-coded ID)
  - Goal: every default `progress_report.py` run prints `Parse/input problems — TODO.md: task M8.A1 not found`, because `L4_PREREQ` hard-codes `M8.A1` while `M8.A2`'s block now says `Depends: — (M8.A1, M8.A4 and M8.A5 are merged)` and the block is gone. The dashboard therefore cannot show a checked L4 prerequisite, and a reader cannot tell "missing from this TODO" from "this TODO is broken". QA 2026-11-16 hit it on the first post-#171 run.
  - Precheck: `python3 tools/progress_report.py | grep -n 'M8.A1'` prints the problem line and `prereq 'M8.A1': checked=None · None`; `grep -c '\*\*M8.A1' TODO.md` prints 0.
  - Scope: `tools/progress_report.py` only, `L4_PREREQ` and the problem text: resolve a prerequisite ID the way a block is named (merged/archived note in the dependent block, or the history files H60 will classify) and either point at the live stand-in or print `archived` instead of `task not found`; same for any other `*_PREREQ` entry that names no block. Not: adding M8.A1 back to the board, editing M8.* blocks, or changing the layer verdicts.
  - Input: `tools/progress_report.py` (`L4_PREREQ`, `_build_manual_layer`, the `problems` collector), TODO `M8.A2` block, `docs/research/todo-history-2026-11-*.md`.
  - Done when: `python3 tools/progress_report.py` exits 0 and prints no `task M8.A1 not found`; the L4 prerequisite line names a live block or says `archived`; `--selftest` (or the synthetic fixture the tool already uses) covers one missing-prereq case; `selftest.py --only progress_report` passes.
  - Stop: if `progress_report.py` has no fixture mechanism, add only the resolution + a `--json` assertion in `--selftest`, and record in the EXP that H60 will take over the general case; do not fork a TODO parser.
  - Claims: C-3850–C-3859

- [ ] **H66 — H64's `--json` parity rule: a follow-up to the parsed-then-unused flag class**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (`tools/claims_check.py` is on `main`); coordinates H58 (the *command* form of evidence) and H61 (the *name*)
  - Goal: H64's navigator caught `--json` parsed then unused — the third such flag this week (SM retro-5 `Watch`). `claims_check` proves a command exists (H58) and the EXP file exists (H61), but nothing proves an evidence command actually *wrote* the file it names, and nothing scans for a flag the tool accepts but never reads. The four claims this pass (`C-3493`, `C-3494`, `C-3840`, `C-3843`) already show the weak spots: `…` in the command span and "same command as C-3840" (prose reference, no invocation). Make "the evidence command writes the named path" a check, not a reviewer's memory.
  - Precheck: `grep -nE "'…'|same command as" docs/research/claims.md | grep -E 'C-349|C-384'` prints the four rows above; a flag-audit script today (`for f in tools/*.py`: collect `add_argument("--x")`, count `args.x`) lists ≥10 flags with zero `args.<dest>` uses (e.g. `sh4dis --check-real`, `l3check --build-corpus`, `one_tile_pipeline --factory-tile`) — the same class H64's `--json` was, not all bugs but all unproven.
  - Scope: `tools/claims_check.py` + a small `--flag-audit` mode only, no vendor data. (1) In `bad_evidence()` (H58's parser) treat a `…`/`...` inside the command span and a bare prose reference (`same command as C-xxx`) as non-runnable, not just the `START`/`MODULE` placeholders. (2) `--flag-audit` sweeps `tools/*.py` for `add_argument` whose `dest` is never read and lists them as warnings; a flag on a `VERIFIED (tool)` claim's own command is an error under H58's `--strict`. Not: editing any claim (that is the task that owns the EXP), auto-fixing flags, or executing the evidence commands.
  - Input: `tools/claims_check.py` (`ROW_RE`, `parse_claim_rows`, `bad_evidence` from H58), `docs/research/claims.md` rows `C-3493`, `C-3494`, `C-3840`, `C-3843`, `tools/one_tile_pipeline.py` `--json` (the H64 fix to model the parity after), `tools/selftest.py`.
  - Hints: a flag can be legitimately parsed-then-forwarded (`args` passed to a helper), so resolve the dest through a one-hop `getattr`/kwargs pass before calling it unused; keep `--flag-audit` warning-only for the legacy flags (`--selftest`, `--check-real`) and make only a *claim-evidence* flag an error. The positive control is `one_tile_pipeline --json` (parsed, writes, selftest re-parses); the negative is `--check-real` (`sh4dis`), which is real but not evidence.
  - Done when: `python3 tools/claims_check.py --selftest` covers a `…`-in-command row, a `same command as C-x` row, and a clean `--json PATH` row (first two fail under `--strict`, third passes); `python3 tools/claims_check.py --flag-audit` lists the unused flags and names the four window claim IDs; `--strict` exits 1 on the current ledger naming `C-3493`, `C-3494`, `C-3840`, `C-3843`; default stays exit 0; `selftest.py --only claims_check` passes.
  - Stop: if the flag sweep has too many false positives (forwarded args), ship only the `bad_evidence()` prose/`…` rule (the H58 extension) and record the flag sweep as `NOT SHIPPED: <reason>` for a later task; do not suppress a real claim-evidence flag.
  - Claims: C-3870–C-3879

- [ ] **H60 — `todo_check`: a `Depends`/`Unblock` ID must resolve to a live block or an archived one in `todo-history-*.md`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/todo_check.py` is on `main`); coordinates H53 (owns `--strict`)
  - Goal: the PO archive pass (2026-11-15, 21 blocks) is a manual fixpoint run by a script, and its only guard was "all 21 present exactly once" after it had already dropped the H blocks from the history file. Board hygiene still cannot tell a *ghost* ID from an *archived* one: `todo_check.py` reports both as `Depends references unknown task ID`. On the current board that is 16 warnings (H24, H26 ×3, M9, M1.12, M1.2b/c, M3.1, M4.5, M4.7 ×2, M4.8c, M9.1, M9.3/M9.4) and a fresh archive can add more without any gate noticing.
  - Precheck: `python3 tools/todo_check.py | grep -c 'references unknown task ID'` prints `16`; `git ls-files docs/research/todo-history-*.md` is non-empty, so an archive exists to resolve against; `python3 tools/todo_check.py --strict` still exits `2` (H53 owns the flag — this task must not add a second one).
  - Scope: `tools/todo_check.py` only: build a `history_ids` set from `[x]` block headers in `docs/research/todo-history-*.md` (reuse the existing block regex, do not write a second parser) and split the current single warning into (a) `Depends/Unblock references archived task ID 'X'` — informational, resolves to a done block, (b) `… references ghost task ID 'X'` — an error under H53's `--strict`, a warning by default, (c) `… references blocked task ID 'X'`. Add a `--selftest` with a temp board plus a temp history: an archived ref warns, a ghost ref fails under `--strict`, a live ref is silent, and a history file that repeats an ID exactly once stays clean. Do not change the default exit code (0 on the current board).
  - Input: `tools/todo_check.py` (`check()`, `_parse_depends`, `known_ids`), `docs/research/todo-history-2026-11-15.md` (the archive format the PO wrote), TODO rules 9/15 and H53's `--strict` note.
  - Hints: `H53` decides which warnings become errors; this task only makes the three cases distinguishable. Resolve `M8.C1…C22`-style range IDs to their base (`M8.C`) the way the block headers do, or they flood the report. If a history file is absent (fresh checkout), degrade to today's single warning, never to an error.
  - Done when: `python3 tools/todo_check.py` still exits 0 and prints the archived/ghost/blocked split with counts; the selftest's ghost fixture exits 1 under whatever flag H53 lands (or under `--selftest` if H53 is not merged); a temp copy of `TODO.md` with one archived ID changed to `H99` is reported as ghost; `selftest.py --only todo_check` passes.
  - Stop: if H53's `--strict` shape differs from the plan above, implement the classification as warnings only and record in the EXP which rule H53 must pick up; do not fork a second TODO checker.
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

- [ ] **H77 — `fn_audit`/`claims_check` do not skip fenced code blocks, so an EXP that quotes a citation becomes a live citation**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M1.26 (done: the l3 scope and its overlay), H76 (done: the l3 image assertion)
  - Goal: in H71 the driver's first EXP draft put the probe text `Goal: fn 0x<VA> probe` inside a fenced block; `fn_audit.citations_markdown` has no fence state, so the EXP became a live l3 citation and the gate went `CORPUS STALE: 1 new` (full `selftest.py` RED). It was worked around with a `$VA` placeholder — a workaround that every future EXP writer must know. Fenced blocks are the documented way to quote a command; a scanner that treats their contents as prose will keep producing this class (the same failure in the docs scope is silent, because `docs/format/*.md` has few fences). This is a *policy* decision, so it is a pair, not a solo edit.
  - Precheck: `python3 -c "import re;t=open('docs/experiments/EXP-2026-11-16-H71-evidence-spans.md').read();print(bool(re.search(r'(?s)\`\`\`.*?fn 0x[0-9a-f]{6,8}.*?\`\`\`?',t)))"`; append a fenced `fn 0x<start>` to a copy of a `docs/format/*.md` and run `python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet` — today it prints `CORPUS STALE: 1 new` for a fenced line.
  - Scope: `tools/fn_audit.py` (`citations_markdown` and the `TODO.md` open-block scanner) gain a fence state: a `\`\`\`` (or `~~~`) block in an EXP/`docs/format` file is skipped, while a `TODO.md` task block keeps its current rule (TODO.md has no fences). Refresh the docs base and the l3 overlay only for the citations the change *removes* (if any), with an EXP that states the before/after counts. Not: changing the `strict` kind rules, the US-build skip, or the pin path.
  - Input: `tools/fn_audit.py` `citations_markdown`/`citations_open_tasks`; H71's `Correction` (the workaround); M1.26's `--scope l3` overlay; `docs/experiments/TEMPLATE.md` (the fenced commands).
  - Done when: a fenced `fn 0x…` appended to a copy of `docs/format/firmware.md` (and to an EXP) does **not** change either `--corpus` verdict (exit 0, unchanged counts); an unfenced one does (`CORPUS STALE: 1 new`, exit 1); `python3 tools/fn_audit.py --selftest` covers both, and `python3 tools/selftest.py` stays green; a before/after count of fenced citations (if any) is in the EXP.
  - Stop: if a fence-aware scanner would change any committed snapshot row, say so in the EXP and ship the scanner with a *new* overlay rather than silently rewriting the frozen one (H69's rule).
  - Claims: C-4000–C-4009

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
- [ ] **H82 — Stamp the zlib interpreter into recompression evidence (this host's default `python3` is zlib-ng)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/zlibinfo.py` exists); coordinates H58/H66 (evidence form) and every `*.cmp`/`LEV3456R` writer claim
  - Goal: on this host `python3 --version` prints `Python 3.15.0` and `python3 tools/zlibinfo.py` prints `zlib: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)`, yet several EXPs in the window write `python3 3.13.1` (H76/H75/H71) or `python3 3.15.0` (M1.31/M1.26/H74) without saying which interpreter has stock zlib 1.3.1. AGENTS.md makes a byte-identical recompression claim unverifiable on zlib-ng, so the field must name the interpreter that produced the bytes, not the one that printed a log line: `python3.13` here is 1.3.2 and `python3` is zlib-ng, so neither default is the 1.3.1 the writer claims assume.
  - Precheck: `python3 tools/zlibinfo.py` exits 0 and names `zlib-ng`; `python3 tools/zlibinfo.py --require-stock-zlib` exits 3 with `needs stock zlib` (so the tool already knows, the EXPs do not use it).
  - Scope: `docs/experiments/TEMPLATE.md` (one line in the Tools row), `prompt_common.txt` (one bullet), and `tools/zlibinfo.py` (a `--stamp` mode that prints nothing on a standard stock runtime and a `WARNING` line otherwise, so a log is self-describing). No tool's compression behaviour changes; no claim is rewritten.
  - Input: `tools/zlibinfo.py` (`classify`, `Runtime.reference`, `--require-stock-zlib`), `docs/experiments/TEMPLATE.md` Tools row, `prompt_common.txt`, EXP-2026-11-05-06-cmp-writer (the `python3.13` precedent), AGENTS.md "Writing data back".
  - Hints: the pin is stock zlib **1.3.1**, and the two interpreters on this host are 1.3.2 and zlib-ng — so the correct field is the `zlibinfo.py` line or `zlib 1.3.1` only when the run really used it. Do not change `--require-stock-zlib`'s exit codes; EXPs that legitimately record `UNVERIFIABLE` keep their exit 3.
  - Done when: `python3 tools/zlibinfo.py --stamp` prints nothing on a stock 1.3.1 runtime and one `WARNING` line on any other (a `--selftest` case, both injected); TEMPLATE's Tools row and `prompt_common.txt` require the `zlibinfo.py` line for any recompression claim; `python3 tools/selftest.py` stays green.
  - Stop: if a per-EXP edit of the window's six files would touch claims, ship the template/prompt/stamp half and record the EXP backfill as a one-line follow-up (never retype a tool version).
  - Claims: C-4050–C-4059

- [ ] **H83 — A board-ref lint: every `TASK#ref` resolves, and a task's normative text never re-states its priority**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H77 (fence-aware scanners, same tool family); coordinates H53 (`todo_check --strict`)
  - Goal: the board's priority prose has rotted repeatedly in ways no gate sees: the header said "next batch: M1.31 → M1.26 → M1.22b" after all three merged, "Take first" listed H74/H75/H71 as ready after they merged, Q1 listed M9.12 "only after M9.31" while M9.12 is blocked *on* M9.31, and H53's block described a `--strict` that had existed for 11 cycles. Each of those cost a cycle of re-derivation, and the mechanics exist already (`todo_check` parses every block). Make the two mechanical classes fail loudly, so a stale sentence is a red gate, not prose archaeology.
  - Precheck: `grep -c 'next batch' TODO.md` and `grep -c 'Take first' TODO.md` show the prose is hand-maintained; `python3 tools/todo_check.py` exits 0 today, so no gate sees it. Print the current count of task-ID mentions in the Priorities section (`python3 - <<'EOF'` probe in the Scope) as the baseline.
  - Scope: `tools/todo_check.py` only (a `--board-refs` mode, on by default as warnings, errors under `--strict`): (1) every `**ID**`/`**ID` mention in the Priorities section resolves to a block that still exists; (2) a `Take first`/`next batch` line that names a task is flagged when that task's `Status` is not `open`/`blocked`; (3) a *done* task named as the current blocker of an open one (`Depends:`/`Unblock:`) is a drift report, not an error (the PO may deliberately keep the history). No prose rewrite; the PO edits on the report.
  - Input: `tools/todo_check.py` (`check()`, block parser, `--strict`), TODO.md Priorities/take-first sections, the retired H53/H74/H75/M9.12/M9.31 sentences as the negative fixtures.
  - Hints: rule 15 drifts are already a `todo_check --strict` error class in H53; reuse its parser, do not add a second markdown reader. Treat `H81`-style blocks ("close the seven…") as naming a set, not a blocker, or the lint will cry wolf on the cleanup task itself. A `done` task inside a historical sentence ("Cycle 8 merged **M1.31**") is legitimate — only a *ready*/blocker claim is wrong.
  - Done when: a fixture Priorities line naming a done task as "next" fails under `--strict` and warns without it; a sentence naming a done task as history passes; `python3 tools/todo_check.py` exits 0 on today's board and prints the board-ref warning count; `python3 tools/selftest.py` stays green; the EXP records the before/after stale-ref count on the real board.
  - Stop: if distinguishing "history" from "next/before" needs natural-language judgement beyond a fixed verb list (`next`, `then`, `Take first`, `ready`, `blocked on`, `only after`), ship the `#ref`-resolves half (pure mechanics) and record the prose half as `NOT SHIPPED: <reason>`.
  - Claims: C-4060–C-4069

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


- [ ] **H89 — The 1,259 unexplained `fn_match` NOMATCH are the next census: rewrites or a second matcher class**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M1.22b (which classified the 13 cited readers and left 1,259 unexplained)
  - Goal: after M1.22b the module census is `UNIQUE 2392 / DIFFERENT 3214 / CALLORDER 213 / AMBIGUOUS 518 / NOMATCH 1259` (total 7596). The 1,259 are unexplained: each has no hash hit, no unique masked-form twin and no call-order match. Decide per sample whether they are real rewrites (a differing instruction) or a second matcher class (e.g. reordered basic blocks, a different register allocation with the same semantics, a function split/merge), so a future leaf/reader task knows whether the US code is missing or the matcher is.
  - Precheck: `python3 - <<'EOF'` (the M1.22b census script) prints `NOMATCH 1259`; `python3 tools/fn_match.py match archive/head256.img archive/us256.img --module Navi.exe --va <one unexplained VA> --json /tmp/x.json` carries `diff: null` and `verdict: NOMATCH`.
  - Scope: a sampling study, not a matcher change: pick a counted random sample of the 1,259 (state the seed and size), classify each by disassembly (same opcode stream with a reordered block / different register allocation / genuinely different), and publish the distribution with the first differing instruction per sampled function. `tools/fn_match.py` changes only if the study finds one class that is cheap and safe to add (and then it is a separate task).
  - Input: `tools/fn_match.py` (`_pool_only_twin`, `code_digest`, `leaf_compare`), `tools/sh4dis.py`, the M1.22b EXP and C-3626.
  - Hints: this is the same shape as M1.22b, one level down — do not start from a matcher idea, start from disassembly of a handful and let the classes fall out. A sample of 30–50 is enough to size the classes; a full 1,259 classification is not the goal.
  - Done when: an EXP reports the sampled distribution with counts and the first differing instruction per class, and says whether the 1,259 are mostly rewrites or a matcher class; a claim names the dominant class and its evidence; `python3 tools/gate.py` green.
  - Stop: if the sample is all one class with no cheap fix, record it and do not change `fn_match.py`.
  - Claims: C-4120–C-4129

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

- [ ] **H93 — H90's EXP still has an empty "Corrections after navigator review" section**
  - Status: open · Owner: — · Critical: no · Pair: required
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

- [ ] **H94 — H90's EXP sat "done" with hand-typed counts and a broken commands section**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H90 (the EXP it repairs is on `main`; H93 owns the navigator section only)
  - Goal: make H90's EXP re-runnable as written — every count quoted from a command that prints it, the clone recipe one copy-pasteable block that still demonstrates the defect, and the failed-run count consistent with C-4130.
  - Note (SE 2026-11-17): the SE re-ran H90's Done-when (b)-(e) and all pass, but three EXP defects survived the pair: the Record `809 commits, pack 3.2 MiB` and `Tools: git 2.5x, python3 3.15` are typed, not from a command (AGENTS "every number is quoted"); the Method command block lists `git clone … /tmp/x && cd /tmp/x` then a second `git fetch --unshallow` line that would run in the wrong cwd; and "the five `main` pushes whose run failed" contradicts the nine `COUNT` lines and the twelve red pushes the same EXP states. The recipe also now fails as written: on today's `main` a depth-1 clone prints `count check: skipped`, not `9` (C-4131 covers this, the Reproduction block does not).
  - Precheck: `grep -nE '809 commits|git 2\\.5x|python3 3\\.15|five .main. pushes' docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` prints the typed lines; `rm -rf /tmp/x && git clone --depth 1 file://$PWD /tmp/x && (cd /tmp/x && python3 tools/claims_check.py --strict --count-check | tail -1)` prints `claims_check: OK`, not the `9` the Reproduction says.
  - Scope: `docs/experiments/EXP-2026-11-17-H90-ci-shallow-count.md` only: quote `git rev-list --count 3d79bcc` and `git count-objects -vH | grep size-pack`; state the interpreter `python3 -V` prints and `git --version`; collapse the two-line clone recipe into one `( cd /tmp/opencode/x && … )` subshell; change "five" to the actual failed-run count the `gh run list` prints; replace the Reproduction block with the pinned-tool rev from C-4131 (`git show 3d79bcc:tools/claims_check.py` into the depth-1 clone) or mark it "does not reproduce on today's main, see C-4131". No claim rows; H93 owns the navigator section.
  - Input: the H90 EXP, `docs/experiments/TEMPLATE.md`, C-4131/C-4135, `git rev-list --count`, `git count-objects -vH`.
  - Hints: the `12` in C-4130/C-4131 and the H90 Goal is correct (`gh run list` shows twelve `failure` rows before the first post-fix `success`); the "five" is the only run-count defect. Do not re-pin C-4135's `809`/`3.2 MiB` to `main`'s today value — the claim names `3d79bcc`, so quote the number at that commit and say so.
  - Done when: `grep -cE '809 commits|5x|3\\.15|five .main. pushes'` on the EXP is 0 or each hit cites the command that printed it; the clone recipe is one copy-pasteable block and H90's Done-when (b)-(d) still pass as run in H94's EXP. `python3 tools/claims_check.py --strict --count-check` and `todo_check.py` OK.
  - Stop: if the count really cannot be shown from a command at `3d79bcc`, delete the number and point at C-4135 instead of retyping it.
  - Falsifier: the typed `809 commits`/`3.15` strings remain, or the Reproduction block still prints `count mismatch` on today's `main`.
  - Claims: C-4200–C-4209

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

- [ ] **H86 — Make the claims half of the standing gate blocking in CI (todo half after H53)**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: H78 (the count rule inside `--strict`, done), H85 (the runner, done); H53 only for the second half
  - Goal: cycle 9 was planned around `ci.yml` not running `claims_check --strict`, but **H85 already closed it**: the one standing-gate step runs `tools/gate.py`, whose `claims_check` gate is `claims_check.py --strict --count-check`. So `grep -cE 'claims_check\.py --strict|todo_check\.py --strict|--count-check' .github/workflows/ci.yml` now prints `1` (the string `--count-check` inside the gate step's comment/output), and `python3 tools/claims_check.py --strict --count-check` exits `0` on `main`. This task is now the **verification + documentation** half: prove a synthetic count mismatch fails the CI step, and that `.github/workflows/README.md`'s "Hard gate" list names `tools/gate.py`. The **second half** (`todo_check --strict` blocking) stays blocked on **H53** (66 strict errors), where `prompt_qa.txt` and H85's `--board-clean` already provide the switch.
  - Precheck: `python3 tools/gate.py` → `claims_check PASS`; `python3 tools/claims_check.py --strict --count-check` exits `0`; `grep -n "Hard gate" .github/workflows/README.md` shows the old selftest/claims/todo list.
  - Scope: `.github/workflows/README.md` (the "Hard gate" contract text: name `tools/gate.py` and the PASS/FAIL/SKIP policy), and the H86 half of the CI summary wording if it still lists the three old steps. **No** workflow logic change (H85 did it) and **no** `todo_check --strict` blocking (H53).
  - Input: `.github/workflows/{ci.yml,README.md}`, EXP-2026-11-16-H85-standing-gate, H53 block.
  - Hints: the honest result here may be "H85 already did the claims half; H86 is README + a negative CI test". If the negative test needs a real red run, do it locally with the corrupt-snapshot trick (QA verified: a corrupt `image_sha256` gives `step_rc=1`, `gate: 3 pass, 1 fail`) — do not push a red PR.
  - Done when: `.github/workflows/README.md`'s gate list names `tools/gate.py` and the SKIP policy; a local reproduction of the CI step (the `PIPESTATUS` command shape) fails on a synthetic count mismatch and passes on a SKIP-only run; `python3 tools/gate.py` green; `python3 tools/todo_check.py` OK.
  - Stop: if the README's contract already names the gate (it may, after H85), mark this done as "H85 closed the claims half; README updated" with a one-line Result and leave the todo half to H53's follow-up.
  - Claims: C-4090–C-4099

- [ ] **M1.19 — Wire the kernel decompressor into `cerom.py`, `rommap.py` and `va_class.py`**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M1.21 — Decode the compressed `FILESentry` payloads with the kernel routine (re-opens M1.3/M1.4)**
  - Status: open · Owner: — · Critical: no
  - Depends: — (H51)
  - Goal: read the ROM *files* of builds A/B/C (registry hives, `.lnk`, `initflashfiles.dat`, bitmaps, text), which M1.4 could not extract. They tell which drivers and paths the unit uses for the SD card and the map (`\SystemSD\…`), and M8 needs the registry.
  - Precheck: `python3 tools/cerom.py --image-start 0x200200 IMG256 files | head` lists `FILESentry` rows with `nRealFileSize` ≠ `nCompFileSize`.
  - Scope: all `FILESentry` rows of A, B, C on IMG256; extraction to `archive/work/` only. Report names, sizes, SHA-256 and file type — no content in the repo except short ASCII keys that are not vendor data (registry key *names* relevant to SD/map paths are fine; values that are vendor strings are quoted by offset).
  - Input: `tools/nk_decomp.py decompress(data, off, comp_size, real_size)`; EXP-2026-11-06-M1.4 (which rows, what failed); EXP-2026-11-05-M1.2a / -M1.2d (the 22/25-byte section header forms — a file payload may start with a different header or none).
  - Hints: try first exactly as for a section (`skip=0, step=1, block=0x1000`). If `r0 = -1`, read the caller of the file path: `sh4xref.py IMG256 nk.exe --image-start 0x3e00200 --to 0x88037590` (`DECOMP_WRAP`) lists every caller; the one that is not the section loader `0x880385e4` is the file reader and shows the arguments it passes (a per-page call with `skip = page*0x1000` is the usual shape). Positive control: a file whose type has a magic (`BM`, `regf`, UTF-16 text, `MZ`).
  - Done when: the EXP lists every `FILESentry` with `real size / decoded length / sha256 / magic`, at least one file per build decodes to a recognisable type, and a short `docs/research/` note names the registry keys that mention `SystemSD`, the SD driver and the Navi launch.
  - Stop: if no argument set decodes a file with a known magic, write the caller's argument trace and stop.
  - Claims: C-3520–C-3529

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

- [x] **M1.23 — Finish M1.20: wire pdata into `cerom`/`sh4xref`/`sh4scan`/`reader_precheck` and register C-351x**
  - Status: done · Owner: task/m1.23-pdata-wireup · Critical: yes · Pair: required
  - Result: EXP-2026-11-15-M1.23-pdata-wireup; C-3610–C-3619 registered (corrected C-351x restatement). `pdata` labels are live in `sh4xref`/`sh4scan`/`reader_precheck`, `cerom.e32()` has `exception`; `sh4xref --to 0x0041c7dc` prints the pdata holder `fn 0x0041c990`; `selftest.py` 86 passed / 0 failed.
  - Depends: M1.20 (tool on `main`); M1.19 not required (compressed pdata already decodes)
  - Goal: `EXP-2026-11-12-M1.20-pdata-function-table` and its proposed C-3510–C-3519 describe behaviour that `777fb68` did not ship. Finish it so `fn 0x…` labels come from `.pdata` everywhere the EXP says, and the ledger matches the code.
  - Precheck: `python3 -c "import sys;sys.path.insert(0,'tools');import cerom;d=open('archive/head256.img','rb').read(128<<20);print(sorted(cerom.CERom(d,0x200200).e32(cerom.CERom(d,0x200200).module('Navi.exe')).keys()))"` must contain `exception`; `grep -c pdata tools/sh4xref.py tools/sh4scan.py tools/reader_precheck.py` must be non-zero for each.
  - Scope: (1) `cerom.e32()` returns `exception=(units[6], units[7])` (additive key; keep every existing caller/selftest green); (2) `sh4xref.py` `load_module` attaches `mem.fn_of` from `pdata.load_table` when an image+module are given, and `_load_line` prints the pdata start instead of the prologue guess; (3) `sh4scan.py dump` tags pdata STARTs; (4) `reader_precheck.py` `anchor_report(..., data=, image_start=, module=)` labels holder `fn`s from pdata; (5) register C-3510–C-3519, **corrected**: C-3510 asserts the `cerom.e32()` key, which exists only after this task; drop/rewrite its "no module lacks it" wording if the census cannot back it.
  - Input: `tools/pdata.py` (`load_table`, `locate`, `exec_sections`), `tools/cerom.py` `e32()` (`units` is `<18I` at `o+36`), `tools/sh4xref.py` `load_module`/`_load_line`, `tools/sh4scan.py` `cmd_dump`, `tools/reader_precheck.py` `anchor_report`, EXP-2026-11-12-M1.20 §§"Wire-ups", C-3510–C-3519 text at the end of that EXP.
  - Hints: do not re-derive the census; re-run the EXP's §2 commands and paste counts. `nk_decomp.parse_pdata`/`locate` already exist; `pdata.py` is the one to reuse, not a second copy. The EXP's fallback in `pdata.py exception_entry()` (`units[6:8]` when the key is absent) shows the intended contract — pull it up into `cerom` and let `pdata` keep the fallback for older callers.
  - Done when: the precheck grep is non-zero for all three tools; `python3 tools/sh4xref.py archive/head256.img Navi.exe --image-start 0x200200 --to 0x0041c7dc` prints a holder that equals pdata (`fn 0x0041c990`); `python3 tools/selftest.py` passes; C-3510–C-3519 are rows in `claims.md` whose evidence column names a command that now exists; an EXP (`EXP-YYYY-MM-DD-M1.23-pdata-wireup`) records the before/after label for 3 VAs.
  - Note (SE 2026-11-15, TEMPLATE method): the M1.20 EXP's §2 all-module census is a heredoc pinned to `/tmp/opencode/img/IMG256.img` — the only way to reproduce C-3512's totals (A 87,530 / B 21,930 / C 25,243). A claim whose command is a throwaway heredoc on an absolute path is not re-runnable from the repo. Before registering C-3512/C-3514, add a `pdata.py census IMG --json` subcommand (or a `tools/pdata_census.py` with `--selftest`) that prints `module / records / section / compressed` for A/B/C and paste *that* command into the claim evidence. If the census is too slow to run in CI, commit its JSON as a fixture (counts only, no vendor bytes) and make `census --check-fixture` fail on drift.
  - Stop: if a tool's selftest depends on the prologue heuristic in a way pdata cannot satisfy, leave that tool on the heuristic, list it in the EXP, and register only the claims the code backs.
  - Claims: C-3610–C-3619

- [ ] **M1.32 — Give the M1.22 US reuse points one owner: `targets.json` starts, `point_walk_l3`/`chunk_decoder_l3` tables, the fn_audit skip set, the EXP, the format doc**
  - Status: open · Owner: — · Critical: no · Pair: required
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
  - Claims: C-4160–C-4169

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

- [ ] **M1.24 — `sh4literal`: one literal-pool scan that reports referenced vs unreferenced 32-bit words**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: — (uses `sh4dis`/`pdata` when the image is given)
  - Goal: three recent negative results ("never read") rest on ad-hoc sec0 literal surveys pasted into EXPs (M3.13 pass-3; M3.11c/M3.15 earlier) and are not reproducible from the repo. Replace them with one tool so "literal X appears in no pool" is a command, not a story.
  - Precheck: `python3 tools/sh4scan.py --selftest` passes; `grep -n "def load_literals\|class.*pool\|literal" tools/sh4xref.py` shows the pool resolver to reuse.
  - Scope: new `tools/sh4literal.py` (`--selftest`): parse a module's executable sections, collect every PC-relative `mov.l @(disp,PC)`/`mova` target (32-bit pool words) and report per word `VA, word, referencing instructions[]`; query modes `find WORD` / `--range LO HI` / `--unreferenced`; `--module M --image-start S` for a real image, `--json` for EXPs. Also report a module's literal pools **inside decoded INIT sections** when `nk_decomp` can decode them, so "sec1 was not searched" is visible. Not: a disassembler (reuse `sh4dis`).
  - Input: `tools/sh4dis.py` (operand decode), `tools/sh4xref.py` pool logic, `tools/sh4scan.py`, `tools/pdata.py` (function ranges), `tools/nk_decomp.py` (INIT bytes).
  - Hints: M3.13's `:;:` (`0x3a3b3a`), `01 f4 00 00` (`0x0000f401`/`0x01f40000`), `4e 20 00 00` (`0x0000204e`/`0x4e200000`), `0x0000ff00`, `0x0000c000`, `0x0000a000` are the regression corpus — the tool must reproduce M3.13's "0 references" for the first three and its "1 reference" for `0xc000`. Positive control: a known-referenced literal (e.g. `LCTBL001.DAT` address at `0x0017a1f8` loaded by `fn 0x004125a8`).
  - Done when: the tool reproduces the M3.13 corpus in an EXP, including whether the constants appear in **decoded sec1/sec2** (a column the pass-3 EXP lacked); `--unreferenced` on `Navi.exe` sec0 gives a count; selftest covers direct/PC-relative/pool-in-data and a false pool word; `--parent-of VA` prints the true enclosing `fn` start from the pool walker's own operand data (so `0x0041c7e8` prints `0x0041c7dc`), and that command is the re-check H63's `Pin:` line names.
  - Stop: if `nk_decomp` cannot decode a target section, print `NOT SEARCHED (section N)` — never fold it into "absent".
  - Claims: C-3630–C-3639

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

- [x] **M1.29 — `fn_audit`: a documented correction (`0xMID → fn 0xSTART`) is resolved, not `INSIDE`**
  - Status: done · Owner: task/m1.29-fn-audit-corrections · Critical: yes · Pair: required
  - Depends: M1.25 (`fn_audit.py`, done)
  - Goal: M1.25's audit keeps bare VAs on a correction-marker line (`0x00542256 → fn 0x00542250`, `0x00413af4` on M3.22's H51 note) as `ctx` citations and classifies them `INSIDE`, so 3 of the 12 unique `INSIDE` VAs can never be "fixed" without deleting the corrective prose that is the record of the fix. H52's "re-run `fn_audit --fix-list` until empty" and M1.26's "exit 1 on any `INSIDE`" gate therefore cannot reach zero. Teach the audit to recognise a correction pair and stop counting it as an unresolved failure; keep a live mislabel (`fn 0xMID`) a failure.
  - Precheck: `python3 tools/fn_audit.py archive/head256.img --fix-list | wc -l` prints `12` today; `python3 tools/fn_audit.py archive/head256.img | grep -E '0x003f5fc2|0x00413af4|0x00542256'` shows all three as `INSIDE`; each sits on a line that already names its true start (`0x003f5fc2`→`0x003f5f48` on TODO.md:589, `0x00542256`→`0x00542250` on TODO.md:585/775), so a correct line is currently indistinguishable from a wrong one.
  - Scope: `tools/fn_audit.py` only, `--scope docs` corpus and its selftest. A `ctx` citation is `CORRECTED` (not a failure) when the same line also cites `fn 0x<same true start>`, or when the bare VA is immediately followed by `→ fn 0x<start>` where `<start>` equals `pdata.locate`'s start; a bare VA with no correct start on the line, or a `fn 0xVA` citation whose VA is mid-function, stays `INSIDE`. `--fix-list` and the exit code follow the same rule; add a `CORRECTED n` count to the summary. Do not touch the citations (H52) or widen the corpus (M1.26).
  - Input: `tools/fn_audit.py` (`citations_markdown`, `CORRECTION_RE`, `classify`, `Verdict.is_failure`, `fix_list`), `tools/pdata.py` `locate`; EXP-2026-11-15-M1.25-fn-audit §Scope/Observations; the three ctx-only VAs above.
  - Hints: the line already pairs the wrong and the right VA on purpose, so reuse that pairing rather than a new heuristic. Keep `0x0041c7e8`→`0x0041c7dc`, `0x0040e4b2`→`0x0040e28c`, `0x00412bee`→`0x00412ac0` a failure while a mid-function label for the corrected VA remains — they also appear as live `fn`/`const`/`target` citations, so the same VA can be both `CORRECTED` on one line and `INSIDE` elsewhere; report per-citation, not per-VA.
  - Done when: `python3 tools/fn_audit.py archive/head256.img --fix-list` drops the three ctx-only VAs (`0x003f5fc2`, `0x00413af4`, `0x00542256`) and keeps the nine live ones, exiting 1 while any live `INSIDE` remains; `--selftest` covers a correction line that passes and a bare mid-function label that still fails; the corrected count is printed; `selftest.py --only fn_audit` passes.
  - Stop: if the pairing cannot be told from a genuine mislabel without reading intent, record the three as an explicit `accepted INSIDE` allowlist in the tool with a comment and a claim, rather than a regex that can hide a real one.
  - Claims: C-3790–C-3799
  - Result: EXP-2026-11-15-M1.29-fn-audit-corrections.md (C-3790–C-3795; C-3796–C-3799 reserved). `tools/fn_audit.py` adds a `CORRECTED <start>` verdict for a `ctx` citation whose own `→`/`->` pair names `pdata.locate`'s start (repeated bare VA does not inherit it, cross-build map is not a correction) plus an explicit commented `CORRECTION_ONLY` pin for prose that names the start on another line; a live `fn`/`sub_`/target/const label is never corrected, `--fix-list` and the exit code follow `is_failure`, and the summary prints `CORRECTED 13` and the correction-only VAs. On `archive/head256.img` (`92aa525d…`) `--scope docs` is unchanged at 17 files / 297 citations / 112 unique VAs, `INSIDE` occurrences 46 → 33, `--fix-list` 12 → 9 and drops exactly `0x003f5fc2`, `0x00413af4`, `0x00542256`; nine live `INSIDE` VAs remain and exit stays 1. `fn_audit --selftest` 30/30 OK (pair, wrong start, live label, allowlist pin, cross-build map, repeated VA), `selftest.py --only fn_audit` PASS, `claims_check.py`/`todo_check.py` OK. `tools/README.md` documents the class.

- [x] **H101 — PM fourteenth pass: six days of board, a call graph, directions without hardware**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes
  - Depends: —
  - Goal: say how the work went since H51 (2026-11-11), and set research and development directions that need no hardware (Marek, 2026-11-17).
  - Done when: the EXP counts what closed by stream, each direction has a task with hints, and every number in it comes from a committed command.
  - Result: `docs/experiments/EXP-2026-11-17-H101-pm-review.md` (C-4280–C-4289). 33 tasks closed in six days: 22 H, 10 M1, 1 M9, none in M3/M4/M5; of H51's twelve tasks two closed. New `tools/callgraph.py` (M3.23 core): `Navi.exe` EU2011 = 9,000 nodes, 22,867 direct edges, 589 unresolved indirect calls; the map-file layer is 117 functions with three stdio wrappers; the router reader `0x004266ec` reaches 48 functions. H51's C-3488 corrected (281 code pointers in sec1 `INIT`, not 6,052). Rule 17 added.
  - Claims: C-4280–C-4289

- [ ] **H103 — `cardcheck` cannot check a tree we built: no `--generate-fixture`, so L1 can never be a CI row**
  - Status: open · Owner: — · Critical: yes · Pair: required
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

- [ ] **H105 — H40's fixture has no negative control: a tree that passes but cannot fail proves nothing**
  - Status: open · Owner: — · Critical: yes · Pair: required
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

- [ ] **H106 — L3 never runs on the tile L2 actually writes: `tile_reader`'s only corpus is a factory `B28R070R`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M5.34 (done); M9.13/M3.25 are the entry-point work and stay their own tasks — this task only makes the corpus point at *our* tile
  - Goal: `prompt_qa.txt` asks "L3 which firmware-fragment readers ran on **our data**"; today `tools/l3_harness/targets.json`'s `tile_reader` corpus is the factory `MAPAL001/B28R070R.DAT` and the run is BLOCKED (no entry point). So even after M9.13 lands, the first L3 tile verdict would be on vendor bytes, not the `B48R058R` tile M5.34 edited. A corpus row that names M5.34's generated tile (and `one_tile_pipeline --synthetic`'s tile) makes "L3 on our data" a real row when the reader becomes runnable, and today makes the *absence* explicit instead of hidden behind one blocked target.
  - Precheck: `python3 -c "import json;print(json.load(open('tools/l3_harness/targets.json'))['tile_reader']['corpus'])"` names a factory tile; `grep -c B48R058R tools/l3_harness/targets.json` prints `0`; `python3 tools/l3check.py --build-corpus` lists `tile_reader` BLOCKED with that corpus.
  - Scope: `tools/l3_harness/targets.json` + `tools/l3check.py` reporting only — add corpus entries (`generated:m5.34:B48R058R`, `synthetic:one_tile_pipeline`) that resolve to a path when the tree is present and print `NOT RUNNABLE (no entry point)`/`NOT RUN (no tree)` with the reason; no reader work, no verdict change for the blocked target.
  - Input: `tools/l3_harness/targets.json`, `tools/l3check.py` (`--build-corpus`, corpus resolution), M5.34's EXP (tile size/hash as the provenance string), `docs/research/reader-coverage.md` rows 17–19, H43.
  - Hints: the corpus path must not be a vendor path; the row records `ran_on_our_generated_data: false` until M9.13, and flipping it is M9.13's Done-when. Keep one `tile_reader` target (two names would double the blocked count and read as progress — H107).
  - Done when: `python3 tools/l3check.py --build-corpus --json /tmp/opencode/h106.json` prints both generated corpus entries with an explicit status and reason; on a host with the M5.34 tree the status is `NOT RUNNABLE (no entry point)`, without it `NOT RUN (no tree)`; count of targets and `runnable` unchanged; `selftest.py --only l3check` PASS.
  - Stop: if M9.13 lands first and makes `tile_reader` runnable, this must assert our tile is the corpus it *ran* on (the runner's log names the path), not merely that it is listed.
  - Claims: C-4370–C-4379

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

- [ ] **H109 — the four rule-17 map numbers are three Python one-liners, one 10-line shell loop and a host path**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (the PO wrote the commands; this makes them portable and honest when an input is absent)
  - Goal: retro 2026-11-18 beat 4: "no log quotes the four rule-17 counters from a command". The PO's Priorities block now has them, but one is a 10-line `python3 -c` with a shell loop over `/home/marek/.../m5.4/card-factory`, so on a host without the factory tree it crashes instead of saying "NOT RUN" — and QA cannot quote it. One `tools/map_signals.py` prints all four with a stable key each, `LOCAL`/`NOT RUN` where an input is missing, `--json` for the logs.
  - Precheck: `python3 -c "import sys,pathlib;sys.path[:0]=['tools'];from progress_report import parse_reader_coverage as p;…"` (Priorities block) needs `tools/` on the path; the tile one-liner needs `tools/ze0-viewer/tools_ze0` and three `.DAT` files; the P0 one needs `/home/marek/projekty/leafre-work/m5.34/report.json` hard-coded.
  - Scope: new `tools/map_signals.py` with four subcommands or one default (`readers`, `l3_rows`, `tile_bytes`, `card_step`): reuses `progress_report.parse_reader_coverage`, the row awk from Priorities, `clarion_tile.read_tile`, and the M5.34 report's `cardcheck_ok`/`l2check_ok` — one implementation, no new numbers. Exclusion: it must not redefine any metric; if a metric needs a new definition, that is a PO task.
  - Input: the four commands in TODO Priorities (the portable contract to preserve verbatim in output keys), `tools/progress_report.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py`, M5.34's report schema (`cardcheck_ok`, `l2check_ok`, `counts.cardcheck_rc`), `docs/research/reader-coverage.md`.
  - Hints: `card_step` should read the report's booleans *and* print `counts.cardcheck_rc`, because the two can disagree (QA 16th pass: keys `cardcheck_ok`/`l2check_ok` exist beside nested `counts.cardcheck_rc`) — print both, never resolve silently.
  - Done when: `python3 tools/map_signals.py` prints the four numbers on this host; with `--factory-root` absent it prints `tile_bytes: NOT RUN (no factory tiles)` and still exits 0; `--json` carries the same keys the Priorities block uses; `--selftest` uses a tiny synthetic tile + a stub report; `selftest.py --only map_signals` PASS; the Priorities block can cite it as the one command.
  - Stop: if the reader-coverage parser is too coupled to the Markdown table to reuse, wrap it (`progress_report` stays the owner of the row semantics) and record that in the EXP; do not fork the parser.
  - Claims: C-4400–C-4409

- [ ] **H110 — the L4 row of the matrix is prose: M8.A2's boot numbers live only in the TODO block**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M8.A2 (done), M8.A10 (done); M8.A3 invents no new row, it fills this one
  - Goal: `prompt_qa.txt` requires the matrix to show "L4 full-system emulator readiness (what can run, what is blocked)". Today that is four prose lines in TODO's critical path plus the M8.A2 block; a QA pass must re-read EXP/TODO to say "QEMU 8.2.10 `-M ze0` boots one image: 10 s, exceptions 0, one unmodelled `write 0x38`" (C-4311) and "M8.E4 needs M8.A3/A6 + M9.16". A committed L4 panel with one row per stage (`F0`…`F4`), each naming its gate and blocker, and `NOT RUN` when no run log is supplied, makes the L4 delta a row instead of a paragraph.
  - Precheck: `grep -c 'M8.A3' docs/research/test-system.md` prints `0`; the only L4 statements are TODO.md's critical-path bullet and M8.A2's block.
  - Scope: `docs/research/test-system.md` (new §L4) + a small `tools/l4_status.py` (`--run-log PATH`, `--json`, `--selftest`): rows `F0 boot log`, `F1 stable kernel`, `F2 drivers`, `F3 SD mounted`, `F4 Navi.exe headless`, each with `gate`, `evidence claim`, `blocker task`, and `status ∈ PASS|FAIL|BLOCKED|NOT RUN`. `M8.A2`'s boot facts are quoted from C-4311/C-4312, not retyped from the TODO prose. Exclusion: no QEMU build in CI, no assertion that any stage passes.
  - Input: TODO M8 section (M8.A2 result, M8.A3/A6/A8/A9 blocks, M8.E4), C-4310/C-4311/C-4312, `EXP-2026-11-17-M8.A2-machine-skeleton-reprobe`, `tools/qemu-ze0/run.sh` (`--workdir` log names), `docs/research/test-system.md` §status classes.
  - Hints: `--run-log` should read `run.sh`'s summary keys only (exceptions count, unmodelled accesses, wall clock) — those exist; anything absent is `NOT RUN`, never inferred. The panel is readiness, not acceptance (rule 13): say "boots one image", not "L4 pass".
  - Done when: the §L4 table exists with six rows and no bare numbers (each names its claim); `python3 tools/l4_status.py` prints the table and exits 0 with `F4 BLOCKED (M8.A3, M8.A6, M9.16)`; without a run log every F-row is `NOT RUN`; `--selftest` proves the five statuses and that a missing key is NOT RUN; `selftest.py --only l4_status` PASS.
  - Stop: if `run.sh`'s summary format is unstable, print the statuses from the committed table only and mark `--run-log` as best-effort in the docstring.
  - Claims: C-4410–C-4419

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

## M2 — Map code, activation, updater

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
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M3.11c — The name accessor for a `POINT` record**
  - Status: open · Owner: — · Critical: yes
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
  - Claims: C-2920–C-2929 (was C-2548–C-2549, overlap with M3.11b fixed by H24)

- [ ] **M3.13 — The `ADDRE` (address) reader**
  - Status: blocked · Owner: — · Critical: yes
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
  - Claims: C-2180–C-2189
  - Note (SE 2026-11-13): the pass-3 EXP `EXP-2026-11-12-M3.13-addre-reader-3` is the current record; its status line said "done (partial)" and was corrected to `blocked`. Its "never read" labels (C-970/C-975/C-977) are scoped to **sec0 literal pools**; `Navi.exe` sec1/sec2 (decoded by `nk_decomp`) were not searched, so do not read them as "the firmware never reads these".
  - Result: `EXP-2026-11-08-M3.13-addre-reader-2.md` (C-2180–C-2187, partial; refines `EXP-2026-11-06-M3.13-addre-reader.md`). Writer-implied native `u16` class-mask signature finds `fn 0x003f56bc` (Navi.exe sec0, `0x003f56ec`) — sole `*r5 & 0xe000 >= 0xc000` (`cmp/hs` literal `0xc000`, 1/82 loads) gate, accepts ADDRE `c0/c8/c1` (C-973 tag-class mapped). Resolves via `0x003f51e0` (`0x00d53500`, POINT family); callers `0x003f5d98`/`0x003f61bc`. C-970–C-972, C-974–C-977 + sequential `2*L`/token consumers not mapped (done-when not met). L3: `0x0040b358`→`-1`, `0x0040114e` FPU-unmodelled. `refer.md`/`firmware.md`/`reader-coverage.md`/`claims.md` updated.

- [ ] **M3.14 — `ZCODE` / `ICODE001` / `COORD001` readers**
  - Status: blocked · Owner: claude/m3.14-reader-layout · Critical: yes
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52).
  - Blocker: no reader body for `ZCODE0nn` or `COORD001` is in decodable build-A code (their names have no plain literal load; `ICODE001` has only the opener `fn 0x003f2cc0`), so the done-when is not met (C-2190–C-2199).
  - Unblock: **M3.23** (candidate readers by call-graph reachability from the access path; its own deps are M1.20 + M3.24, both open) confirmed by **M9.38** (which function reads the page buffer). `M1.2f`/`M8.E1` are superseded (H51: `nk_decomp.py` decodes 245/245 build-A sections) and must not be named as a blocker (H81 closes them; verified by `va_class.py` that no `INIT` byte is needed). The earlier "derive another signature" family is retired per AGENTS.md.
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
  - Status: blocked · Owner: task/m3.15-lctbl-reader-reopen · Critical: yes
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52). The two character-set strings found in sec1 `INIT` (M3.24) are a lead for the name encoding.
  - Blocker: H49 reopen (sec1 "helpers" are IAT imports `OSMDLL!OSM_isSender`/`OSM_Printf`, C-3443, not compressed code): two writer-inverse signature families derived from `lctbl_records.py`/`lctbl_names.py` parse invariants of stock `LCTBL001.DAT` (SHA-256 `8cab1775…`) — S1 marker `mov.b @(2,Rm),R0` + `cmp/eq #1,R0` (40 B, from marker@+2==0x01) and S2 four slot-length reads `mov.b @(d,Rm),R0` d∈{3,4,5,6} same base (80 B, from +3..+6) — scanned Navi.exe sec0 exec plain (5,553,430 B, VA `0x00011000`) and OBJDLL.dll sec0 exec plain (349,755 B, VA `0x03481000`) with 0 hits each (C-2207). Reachability from `fn 0x004125a8` traced through resolved IAT/non-import CODE callees and `0x00413a6c`/`0x00412ac0`→`0x00404994` inflate path without locating record parsing/string decode; `0x003bc960` is TMC/RDSTM decoding (C-2208). No cited blocker VA is `INIT` (`va_class.py`), so M1.2f not justified. Done-when unmet (no reader VAs, encoding assumed by code UNKNOWN).
  - Unblock: **M3.23** (candidate readers by call-graph reachability from the access path; its own deps are M1.20 + M3.24, both open) confirmed by **M9.38** (which function reads the page buffer). `M1.2f`/`M8.E1` are superseded (H51: `nk_decomp.py` decodes 245/245 build-A sections) and must not be named as a blocker (H81 closes them; verified by `va_class.py` that no `INIT` byte is needed). The earlier "derive another signature" family is retired per AGENTS.md.
  - Former blocker (history): the record walker and string decoder were thought reached only through compressed `Navi.exe` sec1 helpers (`0x0055d924`, `0x0055d954`) (C-2200–C-2206); diagnosis superseded by H49/C-3443.
  - Result: EXP-2026-11-10-M3.15-lctbl-reader-reopen (negative, H49 reopen; done-when not met). Prior: EXP-2026-11-08-M3.15-lctbl-reader.
  - Depends: — (M3.7 located the `LCTBL001.DAT` load at `0x004125a8`; H49: the "compressed" callees were imports)
  - Precheck: `tools/reader_precheck.py --module Navi.exe` / `--module OBJDLL.dll` (all executable sections readable, C-2128). Derive signatures from writer-inverse/L3 observation, not doc grammar.
  - Scope: build-A executable sections (all readable); `.data` tables only via a pointer found in code. `Stop:` after two signature families fail — `blocked` + EXP listing signatures tested.
  - Goal: Polish street/place names go through this table (M4.18 framing, M3.9 collation); confirm framing and encoding from the code.
  - Done when: `refer.md` (or `rdstm.md`) names the record-walk and string-decode VAs and states the encoding the code assumes.
  - Stop: after two signature families (named, with source) fail in sec0 and `OBJDLL.dll` — `blocked` + EXP; a cited VA must carry its `va_class.py` class, and only an `INIT` address may name M1.2f.
  - Claims: C-2200–C-2209

- [ ] **M3.16 — `INTER` / `FRWAY` readers**
  - Status: blocked · Owner: task/m3.16-inter-frway-readers-r2 · Critical: no
  - Note (H51, 2026-11-11): do not try another byte signature. Unblock is now **M3.23** (candidate readers by call-graph reachability from the access path) confirmed by **M9.38** (which functions read the page buffer); check every VA of the earlier EXPs with `nk_decomp.py pdata` first (H52).
  - Blocker: no content reader VA consuming INTER/FRWAY 12-byte table / blob fields found in decodable build-A Navi.exe sec0 (5.56 MB, 0 compressed exec sections, C-2128) after two structural writer-inverse signature families (12-byte scan + 0xffff@+8 + add#12; 0x1108 construction) returned 0 hits; consumed-field mapping unknown (C-2211–C-2213). Shared REFER001 access path is confirmed (C-2210).
  - Unblock: **M3.23** (candidate readers by call-graph reachability from the access path; its own deps are M1.20 + M3.24, both open) confirmed by **M9.38** (which function reads the page buffer). `M1.2f`/`M8.E1` are superseded (H51: `nk_decomp.py` decodes 245/245 build-A sections) and must not be named as a blocker (H81 closes them; verified by `va_class.py` that no `INIT` byte is needed). The earlier "derive another signature" family is retired per AGENTS.md.
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

- [x] **M3.19 — `tools/sh4scan.py`: commit the scan that produced the three negatives**
  - Status: done · Owner: task/m3.19-close-sh4scan · Critical: yes · Pair: pair
  - Note (rule 15, 2026-11-09 PO): M3.20 done (register-AND mask variant / M3.11 pattern text); re-opened. Counts verified 2026-11-09 incl `mask-pair --via-reg`=1 (immediate 0 recorded).
  - Note (rule 15, 2026-11-09 H48 #170): M1.12 import clause addressed by `tools/reader_precheck.py` importing/delegating to `tools/sh4scan.py` (H48, EXP-2026-11-09-H48-reader-precheck-sh4scan, C-3410–C-3411); re-opened for closure once PR #170 merges.
  - Depends: —
  - Blocker: — (former M1.12 import blocker addressed by H48 #170; counts/selftest/EXP addendum already verified per Result).
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
  - Result: done (TL closure 2026-11-09). `docs/experiments/EXP-2026-11-08-M3.19-sh4scan.md` (verification addendum) reproduces all published counts on IMG256.head `92aa525d…` incl `mask-pair --via-reg`=1 @ Navi.exe `0x003715c8/ca/cc`; `sh4scan --selftest` OK; M1.12 import clause satisfied by H48 (`reader_precheck.py` imports/delegates to `tools/sh4scan.py`, EXP-2026-11-09-H48-reader-precheck-sh4scan, C-3410–C-3411). Claims C-2530–C-2539 remain as recorded.
  - Claims: C-2530–C-2539

- [ ] **H40 — L1/L2 generated-fixture contract: deterministic in-process fixture + coherent ZE0 card/tree builder (no vendor data)**
  - Status: open · Owner: — · Critical: yes
  - Depends: H26; H103 (the `--generate-fixture` primitive) and H105 (its `--break` control) — the L1 CI row cannot exist before the tree can be built and made to fail
  - Goal: close H26 gaps (`L1 synthetic`/`L2 tile` NOT COVERED where feasible) with a tiny deterministic in-process fixture representing generated content (roads/names/POIs/geometry) and a coherent ZE0 card tree/image that `cardcheck.py --root/--image` and targeted L2 round-trips can run on in CI (no network, no OSM download, no vendor data).
  - Scope: test infrastructure only. Procedural/committed fixture (no vendor dump, no downloaded OSM extract) and a minimal builder producing coherent DRSTR/MMAIN/tile level tables/headers/REFER001/top-level layout as current tools support. Do not claim firmware acceptance (rule 13); no full M5 compiler coverage.
  - Input: `tools/l1l2_fixtures.py`, `tools/cardcheck.py`, `tools/mkcard.py`, `tools/drstr_ze0.py`, `tools/tilewriter.py`/harness, `tools/imgpatch.py`, `tools/one_tile_pipeline.py` (`--synthetic` already builds a no-vendor card tree, but its `MAPAL001` tile set is not `cardcheck`-coherent — QA 2026-11-17 measured `cardcheck rc=1`, section 2 levels 2/4/5 and section 4 level 1 not in `MMAIN`); AGENTS data rules.
  - Done when: `python3 tools/<name> --selftest` builds the fixture in a temp dir, runs `cardcheck.py` and reports L1 PASS/FAIL per check (JSON), and runs >=1 coherent synthetic L2 round-trip (tile/DRSTR/POI) where supported; CI-safe/deterministic; H26 registry gains runnable entries only where truly covered, else honest NOT COVERED with updated reason. **Negative control:** the same row must fail on a broken tree — `cardcheck --generate-fixture … --break <kind>` (H105) exits 1 and names the check the good tree passed, so `l1l2-fixtures.yml` cannot go green on a checker that stopped checking.
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
  - Depends: H27, H41, H28, H55
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

- [ ] **M3.22 — Who writes the `0x00d53500` table (HDLMAP / RDSTM schema)**
  - Status: open · Owner: — · Critical: yes
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
  - Claims: C-3460–C-3469

---

- [ ] **M3.23 — Static call graph of `Navi.exe` (pdata + pools + dispatch tables), and readers found by reachability**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M3.24 — Dispatch tables in `Navi.exe` sec1 `INIT`: who is called indirectly**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M3.25 — The tile reader's *entry* VAs: one runnable tile target so L3 can read the file L2 writes**
  - Status: open · Owner: — · Critical: yes · Pair: required
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
  - Claims: none yet

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


- [ ] **M3.27 — M3.25's first half: the tile reader's entry arguments, static, no run**
  - Status: in progress · Owner: task/m3.27-tile-reader-args · Critical: yes · Pair: required
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
  - Claims: C-4580–C-4589

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
  - Unblock: M4.37 (bit-packed coordinate control; if it finds coordinates, re-test 0..2047 here) and M4.27 (remaining index/mixed classes), or an independent firmware/entrance-point method that pins local scale/origin.
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
  - Blocker (history, negative EXP kept): **impossible with current inputs / blocked by compressed `.data` (Navi.exe sec1)**. Precheck: `sh4dis Navi.exe --image-start 0x200200 --check-real` OK on IMG256 `92aa525d…` (M1.11c RDSTM pins, no `.word` gap at named walk sites; MOVT/SHAR/SHLD/SHAD done). `cerom va2file 0x00d53500` → unmapped (`0x-8bb8d900`); `0x00d53500` (schema descriptor consulted by `0x003f51e0`, `[0x003f52b8]=0x00d53500`) lies in **Navi.exe sec1 `va 0x55d000 vsize 0xff16ae psize 0x457c flags 0xc8002040 COMPRESSED rw-`** (covers `0x55d000–0x154e6ae`), so schema bytes/field lengths are unreadable with current inputs. C-884 walk not reproduced to true per-record boundaries; `rdstm_place.py` not re-run on decoded fields; no ≥20 decoded-record mapping, no named join key, no ~0 random-key control. Done-when **not met**. Join/placement route remains **M4.16d** (once true decoded TMC fields exist).
  - Reopen note (H50, rule 15, EXP-2026-11-10-H50-va-class-prechecks): cited blocker VA `0x00d53500` = BSS sec1 +0x7f6500 (zero at load; find writer/runtime init, not M1.2f). Boundary VAs explicit: `0x0055d000` = IAT `COREDLL!Sleep` (sec1 start mention), `0x00ff16ae` = BSS (range end mention). Rerun via M3.22 (writer) + M9.35 context; do not claim M1.2f unless an INIT VA is identified.
  - Unblock: (H49) **M3.22** — `0x00d53500` is BSS (C-3442), decompressed sec1 is zero there; the schema is written at run time. Old wording: `M1.2f` and/or `M8.E1/M1.2g/M9` verified path yielding **Navi.exe sec1 decompressed bytes** for build A (so `0x00d53500` schema contents are readable). M1.11c walk opcodes are done and **not** an unblocker.
  - Re-opened (PO grooming 2026-11-09, rule 15): M1.11c merged; decoder-gap blocker no longer holds. Re-blocked on schema bytes in compressed sec1 (this task).
  - Result (negative, prior): EXP-2026-11-08-M4.16b-record-framing — gate passed (five functions plain in Navi.exe sec0; callees verified); walk not run; done-when not met.
  - Result: EXP-2026-11-08-M4.16b-rdstm-field-walk (negative/blocked: schema `0x00d53500` in Navi.exe sec1 COMPRESSED `rw-`, unreadable; walk/boundaries/placement not reproduced with current inputs). C-2300–C-2309.
  - Depends: M4.15
  - Precheck: `python3 tools/sh4dis.py IMG256 Navi.exe --image-start 0x200200 --check-real` (M1.11c pinned window) confirms no `.word` gap at M4.16b walk sites; `python3 tools/cerom.py --image-start 0x200200 IMG256 va2file 0x00d53500` resolves schema-table location (or records it as compressed `.data`).
  - Goal: reproduce the per-record length/offset directory walk from bytes to recover true TMC field boundaries, then re-run `tools/rdstm_place.py` on decoded fields (location/area/front/rear/inter-section).
  - Scope: the C-884 directory walk (`0x003f56bc`, `0x003f5e10`, schema `0x00d53500`) on Navi.exe build A; ≥20 decoded records tested for placement. No RDSTM writer.
  - Done when: ≥20 decoded records map to tile/mesh/coordinates with a named join key and ~0 random-key control, or the mapping is proven impossible with method recorded.
  - Stop: if schema table `0x00d53500` is unreadable (compressed `.data`) or the walk cannot be reproduced with current inputs, set `blocked` naming that dependency and keep the negative result.
  - Claims: C-2300–C-2309 (was C-1840–C-1849, a collision with M5.1b)

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
  - Claims: C-2490–C-2499
  - Blocker: the `0x18c` codes have no code→language anchor in the four images (only counts agree: US 2/2, EU 8 vs 7 and 17 vs 16); `DRSTR001` `0x18c` is a node listing offset, not a language list (C-2493). The header fixes and the BICON001 retraction are done. See EXP-2026-11-08-M4.22-identity-codes.
  - Unblock: M4.38 (decode the `0x18c` code table from the ICODE001 per-language index or a firmware language table; OQ-44)

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

- [ ] **M4.37 — Prove or refute that bit-packed `POINT` pages carry coordinates (one-command control)**
  - Status: open · Owner: — · Critical: yes · Pair: required
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

- [ ] **M4.38 — Identify the `0x18c` language-code table (unblocks M4.22)**
  - Status: open · Owner: — · Critical: no · Pair: required
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

- [ ] **M4.36 — Link `ADDRE`/`POINT` records to the tile section-4 index (road-name and place lookup key)**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M3.13 (ADDRE reader), M3.9 (section-4 index, done), M4.16b
  - Goal: the L2 reader model today decodes tile section 4 (admin/place-name index) and the odd name section separately, but no task proves how an `ADDRE` id resolves to a *named* street through the section-4 index. Routing and map display need that join; without it a generated Polish tile renders roads with no names even when every record is structurally valid.
  - Precheck: `python3 tools/ze0-viewer/harness.py info B48R058R.DAT` shows non-zero section-4 entries; `python3 tools/addre_reader.py --selftest` (or M3.13's tool) passes; on a factory EU tile, one known street name from `B48R058R` decodes through section 4 to its `ADDRE` record.
  - Scope: factory EU 2011 `B48R058R` and one US tile; `docs/format/refer.md` §section-4, `tile section 4` claim rows, `tools/ze0-viewer` readers. Not: the `REFER002` EV layer, not POI. No new vendor bytes committed — offsets/counts/hashes only.
  - Input: `docs/format/tile.md`/`refer.md` section-4 pages, M3.9 EXP, M3.13 ADDRE reader, `tools/ze0-viewer/tools_ze0`, US `ADDRE`/`POINT` share ids (AGENTS "Format facts").
  - Hints: AGENTS already states `ADDRE`/`POINT` share ids and the join is street + house number; the open question is which section-4 field indexes the name (offset vs ordinal) and whether US stores `ltntbl.dat` case-sensitively. Start with one street whose name is unique in the tile (positive control) and one absent street (negative).
  - Done when: an EXP table `tile / section-4 entry / name / ADDRE id / how resolved` covers ≥ 10 names on EU and ≥ 3 on US with a negative control, `docs/format/refer.md` gains the join, and the viewer `info` prints the resolved name for at least one record. Reader-coverage row updated; L3 reader VA named if M3.13 has one.
  - Stop: if the join is not one-to-one, record the ambiguity classes (same name on two streets, unnamed ways), and stop at the mapping table.
  - Claims: C-3670–C-3679

- [ ] **M4.39 — Route-link id: what in a `MAPAL001` tile section 2 can a `LCTBL001` road or an `ADDRE` record be joined to**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.37 (the L2 graph model this task needs to name nodes/links), M4.31 (the negative join search this narrows); M3.6 (which sections the router reads, done)
  - Goal: routing needs a stable key from a displayed road name/record back to the graph edge the router uses. M4.31 proved there is no `LCTBL↔RDSTM` join and M3.7 showed `RDSTM001` is TMC, not routing; nobody has asked whether section 2 itself carries an id an `ADDRE` name can reach. Without it the map routes on an anonymous graph and "route across the moved road" (M6.7) cannot be aimed at a chosen OSM way.
  - Precheck: `python3 tools/tile_diff.py B48R058R.DAT --section 2` lists section-2 records (M4.23/M4.24 framing); `python3 tools/ze0-viewer/harness.py info` shows section 2 non-zero; `grep -rn 'link_id\\|link_id\\|edge_id' tools/ docs/format/` prints nothing outside the M4.31 negative, i.e. the key is unnamed today.
  - Scope: factory `B48R058R` (and one second tile) section 2 only, offline: enumerate every field that could be a link/node id, test each as a join key against the name layer (section 4 + `ADDRE` from M4.36) and against `LCTBL001`, with a shuffle null control. One EXP table + one candidate key or a negative. No writer, no firmware run; do not re-open M4.31's RDSTM test.
  - Input: `tools/tile_diff.py`, `tools/rd_restrictions.py` (section-2 framing), M4.23/M4.24 grammar, M4.31 EXP (negative), M4.36 (name layer), `docs/format/map-tiles.md` §section 2, `docs/format/refer.md`.
  - Hints: section-2 part b is not decoded (M4.23 open), so restrict to record-level fields that survive the framing; a key that only works on one tile is not a key. The M4.31 lesson: state the join key and corpus size up front, and treat row order as a last resort, never a result. If the only id is a node coordinate pair, say so and propose the coordinate join as the hypothesis for M4.36 to test.
  - Done when: the EXP lists every section-2 field tested, the join rate against the name layer and against `LCTBL001` for each, the shuffle/null baseline, and either names a key that beats its null (with a second-tile control) or records the tested fields as a controlled negative; `docs/format/map-tiles.md` gets the field table.
  - Stop: if no field survives the framing on two tiles, record the negative with the null and stop; do not fit a key from row order.
  - Falsifier: a claimed key scores no better than its shuffled null, or works on `B48R058R` and not on the control tile without a named reason.
  - Claims: none yet

- [ ] **M4.40 — Tile section 2 (route graph) grammar read from the router's reader, not guessed from bytes**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M3.25 (entry and arguments of the tile reader; this task can start from the VAs below without it), M9.38 helps (read-watch)
  - Goal: a generated map cannot route until we can write section 2, and its part b has resisted three byte-level attempts (M4.23, M4.24, M4.3 blocked). The code that parses it is small and isolated: the router data reader `0x004266ec` (EU2011, M3.6) reaches 48 functions with one unresolved indirect call (H101). Read the grammar off that code.
  - Precheck: `python3 tools/callgraph.py reach g.json 0x004266ec` prints `reaches 48 functions, 1 unresolved indirect calls`; `python3 tools/callgraph.py callers g.json 0x004266ec --depth 3` shows `0x00427870` ← `0x00427144`/`0x00427c90` ← `0x00427a34`.
  - Scope: the 48-function subtree, EU2011. Output is a field table for the section-2 record (offset, width, endianness, meaning or `unknown`, the VA that reads it) and the loop structure (what counts records, what ends one). Check each field on factory `B48R058R` and one second tile with `tools/tile_diff.py --section 2`. No writer.
  - Input: `tools/sh4dis.py`, `tools/callgraph.py`, `tools/rd_restrictions.py` (the framing M4.23/M4.24 already have), EXP-2026-11-06-M3.6 (MAP_DATA `0x00425f40` renderer / RGD_DATA `0x004266ec` router, shared `0x0041ee14`), `docs/format/map-tiles.md`. The subtree imports `CreateFileMappingW`/`MapViewOfFile`: the tile is memory-mapped, so the reader takes a pointer — the easiest kind of function to run in L3.
  - Hints: the renderer subtree `0x00425f40` has the same size (48) and shares `0x0041ee14` — diff the two callee sets first; what only the router calls is the section-2 parser. In SH-4 a record field read is `mov.b/mov.w/mov.l @(disp,Rn)` off one base register: list the displacements per function and you have the struct. A Ghidra decompile of these 48 functions (M9.2, runnable on Marek's host) turns days into hours; without it use `sh4dis` and the read-watch tracer. Run the entry in PySh4 with the factory tile mapped and watch which bytes of section 2 are read and in what order: the read order is the grammar.
  - Done when: the field table is in `docs/format/map-tiles.md` with the reading VA per field; `tools/rd_restrictions.py` (or a new `tools/sec2.py`) decodes part b of both tiles with 0 bytes unexplained or lists the unexplained ranges; M4.23/M4.24/M4.3 get an `Unblock:` line pointing here.
  - Stop: if the subtree turns out to hand section 2 to another task by message (an `OSM_TaskSend` with the buffer), name the receiver and stop — that is the next subtree.
  - Falsifier: a field the table gives does not vary where the two tiles' roads differ, or the L3 run reads bytes outside section 2 only.
  - Claims: none yet

- [ ] **M4.41 — Differential decoding: the same tile in 2011, 2014 and 2016**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (three EU images are on the allowed host)
  - Goal: three editions of the same map are the cheapest oracle for field meaning. A tile where one road was added between 2011 and 2014 shows which bytes of section 1, section 2, section 4 and `LEV3456R` belong to one road. No firmware and no hardware.
  - Precheck: `python3 tools/fetch_image.py --image EU2014 -o PATH` and `--image EU2016` verify; `python3 tools/diff_years.py -h` runs.
  - Scope: all `MAPAL001/B*R.DAT` of the three editions: per tile, per section, size and SHA-256; then the 20 tiles with the smallest non-zero section-1 change. For each: which section-1 records were added/removed, and the byte ranges that changed in sections 2 and 4. No interpretation beyond "changes together with".
  - Input: `tools/diff_years.py`, `tools/tile_diff.py`, `tools/ze0-viewer` (section split), `docs/research/image-versions.md`.
  - Hints: sort by edit distance, not by size change — a renamed street changes section 4 only, a new roundabout changes all three. A tile whose section 1 is identical and section 2 differs is a routing-only edit (turn restriction, one-way): those are the pure samples M4.23/M4.3 never had. Record how many bytes of section 2 change per added section-1 road: a constant is the record size.
  - Done when: an EXP with the per-section change census for all tiles (counts) and the 20-tile table; at least three "one variable" pairs (one added road; one renamed road; one routing-only change) named by tile and offset for M4.40, M4.36 and the section-4 reader (M3.6; **M4.21**, the section-4 writer, is done and archived in `todo-history-2026-11-09.md`) to use.
  - Stop: if fewer than three clean pairs exist, publish the census and say so.
  - Claims: none yet

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
  - Note (H51, 2026-11-11): unowned for three days and it gates what Marek should expect on screen for S2 (M6.6). It is a scan, not research: `python3 tools/poi_copies.py` on the US tree; the full US image is on the allowed host (`fetch_image.py --image US`).
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

- [x] **M5.28 — Provisional OSM→Clarion road class/speed table v0 (compiler-unblocking, L2-testable)**
  - Status: done · Owner: task/m5.28-provisional-roadclass-v0 · Critical: yes
  - Depends: — (M4.2 blocked; M4.17/M5.23 are inputs, not blockers)
  - Goal: unblock the OSM compiler spine with an explicit, versioned *provisional* mapping from OSM `highway=*` (+`maxspeed`/access where available) to Clarion tile class/style/speed values, so generated tiles can be built and validated at L1+L2 without claiming firmware acceptance (rule 13).
  - Precheck: `python3 tools/imf_check.py --selftest` passes; M5.4/M5.22/M5.23 writer/field behavior readable from `tools/tilewriter.py` and EXP-2026-11-08-M5.23; list in-scope `highway=*` values from Dolnośląskie IMF/profile if available.
  - Scope: data/tool file (name stated in PR, stdlib, `--selftest`) consumed by `tilewriter.py`/compiler; covers every in-scope `highway=*` or reports unmapped explicitly. No firmware claim; no M4.2 row key.
  - Input: M5.4 provisional-class behavior, M5.23 `(layer, cls_hi)`, M4.17 negative (class_code hypothesis), IMF highway tags.
  - Done when: every in-scope `highway=*` mapped or explicitly `UNMAPPED` (never silent drop); `--selftest` has positive and unknown-value cases; compiler records `mapping=provisional-v0`; one synthetic L2 tile build using the table passes existing tile checks; EXP states provisional/not firmware-confirmed and the M4.2/M5.3 gap.
  - Stop: if no safe Clarion value can be chosen without inventing semantics, use explicit `UNMAPPED` and refuse to generate that class until resolved.
  - Result: EXP-2026-11-09-M5.28-provisional-roadclass-v0. `tools/roadclass_v0.py` (stdlib, `--selftest`) covers all 17 in-scope `DRIVABLE_HIGHWAYS` with `mapping=provisional-v0` (15 mechanism-confirmed buckets + `busway`/`road` auditable low-provisional placeholders, option a; unknown/OOS `UNMAPPED`+`refuse_generate`, no silent drop) and emits `ze0-road-class-table/1` consumable by `tilewriter.py --class-table`. Synthetic L2 emitted-table build/readback: 12/12 points within 1m, 2 parcels. Provisional, not firmware-confirmed (rule 13); M4.2/M5.3 gaps. C-3040–C-3042.
  - Claims: C-3040–C-3049

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

- [ ] **M5.33 — Make M5.29 synthetic scaffold/tile coherent for `cardcheck`/applicable `l2check` (honest gates)**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.29
  - Goal: close the synthetic-path validator failures reported by M5.29 so the no-vendor milestone can produce actionable L1/L2 gate evidence on a synthetic tree, while keeping factory-backed acceptance and firmware acceptance separate and honest (rule 13).
  - Precheck: `python3 tools/one_tile_pipeline.py --selftest` passes; reproduce `one_tile_pipeline.py --out <tmp> --cell B48R058R` then `cardcheck.py --root <tmp> --partial --ignore-dump-artifacts --fast` and `l2check.py --root <tmp> --partial --no-golden --no-cmp --tiles B48R058R.DAT` failures as recorded in EXP-2026-11-09-M5.29 (MMAIN/section-level alignment; `ze0_mutate`/`clarion_tile.read_tile` `struct.error` on synthetic scaffold tile buffer, e.g. `B30R060R.DAT`). Pass the `<cell>.DAT` file name: `--tiles B48R058R` (a bare cell name) matches **0** tiles and still prints `RESULT: PASS` (C-3566).
  - Scope: `tools/one_tile_pipeline.py` synthetic scaffold/helpers and, only if required by the root cause, minimal fixes in `tools/rebuild_manifests.py`, `tools/tilewriter.py`, or `tools/ze0-viewer` parse assumptions used by `l2check`/`ze0_mutate` — name exact changed functions/files in PR. Do not claim factory parity, do not fetch/commit vendor bytes, do not weaken gates to fake PASS.
  - Input: EXP-2026-11-09-M5.29-one-tile-pipeline, `tools/one_tile_pipeline.py`, `tools/rebuild_manifests.py`, `tools/tilewriter.py`, `tools/l2check.py`, `tools/cardcheck.py`, `tools/ze0-viewer/ze0_mutate.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py`.
  - Done when: on the synthetic M5.29 path, `cardcheck` and applicable `l2check` gates either `PASS` with a coherent synthetic scaffold/MMAIN/tile set or are reported as `NOT-APPLICABLE`/`CANNOT-VERIFY-OFFLINE` only for gates that genuinely cannot apply to synthetic/no-vendor trees — never because of a malformed scaffold. EXP records failing checks before/after, commands, hashes of generated synthetic artifacts, and states `mapping=provisional-v0`, rule 13, L3/L4/L5 unknown.
  - Stop: if making the synthetic scaffold validator-coherent requires factory tile bytes or firmware-confirmed structure not available offline, record the exact dependency and block that specific gate as `CANNOT-VERIFY-OFFLINE` with evidence; do not invent bytes.
  - Claims: C-3420–C-3429

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
  - Depends: M5.11, M5.30, M5.29 (gate report format), M9.12 (card gate, once unblocked)
  - Goal: every Poland milestone so far is a chain of manual commands in EXPs; a bench card needs one reproducible command that names the input OSM extract, writes the card, runs `cardcheck`/`l2check`/`l3check --card` and emits a machine-readable bundle. This is the L1→L2→L3 evidence path the PO prioritises, and it makes each L5 run one variable.
  - Precheck: `python3 tools/l2check.py --help | grep -- --cmp-limit` and `python3 tools/mkcard.py --selftest` pass; M5.30 produces a card that differs from factory only in expected clusters. If M5.11's compiler entry point is not yet stable, name the current one in the EXP and gate the wrapper on it.
  - Scope: new `tools/mkpoland.py` (`--selftest`, synthetic no-vendor fixture): `--osm EXTRACT --factory IMAGE -o OUT.img` calls the Poland compiler, `cardcheck --image`, `l2check --root` on the extracted tree, and `l3check --card` when a runnable target set exists; writes `bundle/manifest.json` (input/OSM SHA-256, tool versions, per-stage PASS/FAIL/SKIP/NOT_RUNNABLE, changed-cluster list) and `bundle/report.md`. Never promotes SKIP/BLOCKED to PASS (rule 13). Not: automatic car/bench execution.
  - Input: `M5.11` compiler CLI, `tools/mkcard.py`, `tools/cardcheck.py`, `tools/l2check.py`, `tools/l3check.py`, M5.29 EPX gate-report format, `profiles/dolnoslaskie*`.
  - Hints: reuse H27 `progress_schema` for status classes so the bundle feeds `progress_report.py`; the L3 stage must report `NOT_RUNNABLE` honestly on a host without the firmware image and never fabricate a verdict. The no-vendor CI path runs the synthetic fixture only.
  - Done when: one command produces a bundle on the committed synthetic fixture; on the factory EU image it produces a bundle whose L1/L2 stages pass and whose L3 stage names runnable/blocked targets; a selftest proves a forced L2 failure makes the command exit non-zero and the manifest records `FAIL`.
  - Stop: if M5.11's CLI is not yet callable as a library or command, deliver the stage runner + manifest with the compiler stage `NOT_IMPLEMENTED` and block on M5.11 naming its entry point.
  - Claims: C-3680–C-3689

- [ ] **M5.36 — L2 golden for the road-class table: an OSM class written to a tile must decode back to the same class**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.16 not required; M5.4 (tile splice, done), M5.28 (`roadclass_v0`, done), H41 (per-feature matrix, open — this task supplies the L2 row it reports, not the reporter)
  - Goal: `roadclass_v0` maps 17 OSM highway classes to a provisional Clarion class, but nothing checks the *round trip* at L2: no test asserts that the class emitted into a tile's road records decodes back to the same OSM class under `l2check`/`clarion_tile`. A wrong table can ship a road drawn as a motorway and every existing gate stays green. This is the cheapest map-quality check that can fail loudly.
  - Precheck: `python3 tools/roadclass_v0.py --selftest` passes and `python3 tools/tilewriter.py --selftest` is 68/68; `python3 tools/l2check.py --help | grep -- --semantic-tiles` exists (the hook this task extends). Confirm no current check compares a decoded class to the emitted class: `grep -rn 'class_code\\|road_class\\|cls_hi' tools/l2check.py tools/ze0-viewer/ze0_mutate.py` prints only writer-side fields.
  - Scope: `tools/l2check.py` (one new check `tile_class_roundtrip`) and one synthetic no-vendor fixture in `tools/l1l2_fixtures.py`: build a tile with a known class table via `tilewriter`, decode it, and compare per-road class to the emitted class. The real-image variant runs on the M5.4 `B48R058R` splice. No format change, no new class value; a mismatch is a failed check, not an `UNMAPPED` excuse.
  - Input: `tools/roadclass_v0.py` (the `mapping=provisional-v0` table), `tools/tilewriter.py`, `tools/ze0-viewer/tools_ze0/clarion_tile.py` (the decoded class field), M5.4 EXP, H41's matrix shape.
  - Hints: if the decoded field is not yet known (M5.23), compare at the level the writer controls and state the field in the EXP; do not invent a class semantics. Keep it a separate check name so H41 can report `L2 roadclass` as its own row. This does not confirm the class is *correct* on the car — only that the pipeline does not corrupt it (rule 13 stays open).
  - Done when: `python3 tools/l2check.py --root <synthetic> --semantic-tiles BxxRyyR` reports `tile_class_roundtrip: PASS` on the fixture and `FAIL` when the fixture's emitted class is mutated by one value; the real `B48R058R` splice reports its class rows; `python3 tools/selftest.py` passes; EXP records the per-class table and the negative control.
  - Stop: if the tile record does not carry a recoverable class for any road (M5.23 not decoded), record `NOT_APPLICABLE — class field not readable` with the field location, and do not fake a pass.
  - Falsifier: the check passes on a tile whose emitted class was deliberately changed to a different value, or a class that decodes differently still reports PASS.
  - Claims: none yet

- [ ] **M5.37 — L2 golden for the route graph: tile section 2 must decode to the same node/link graph the writer emitted**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.4 (tile splice, done), M5.23 (record fields, open — this task is the read-back side and may run on the fields M5.23 pins), M5.16 (which VA/section the router reads; this task checks the L2 model, not the firmware)
  - Goal: the map is also a router: `MAPAL001` tile section 2 is the routing graph (AGENTS: "Tile section 2 (router graph) copy — always preserved verbatim"), and no L2 check proves that a *generated* graph decodes back to the same edges. Without this, a card can render roads but route on a graph we never verified, and every gate is green. This is the L2 prerequisite for `M5.16`/`M4.39` ever becoming useful.
  - Precheck: `python3 tools/ze0-viewer/harness.py info <tile>` shows a non-zero section 2; `python3 tools/tile_diff.py --selftest` passes; confirm what is checked today: `grep -rn 'section 2\\|sec2\\|graph' tools/l2check.py tools/ze0-viewer/tools_ze0/clarion_tile.py` shows decode but no emitted-vs-decoded graph comparison.
  - Scope: `tools/l2check.py` (one check `tile_graph_roundtrip`) plus a synthetic fixture: emit a small edge set into a factory-shaped tile section 2, decode it, compare node/link counts and endpoint coordinates. Real-image variant on the M5.4 splice; preserve-only tiles must still report `preserved`, not `fail`. No new graph grammar claim.
  - Input: `tools/ze0-viewer/tools_ze0/clarion_tile.py`, `tools/tile_diff.py`, `tools/tilewriter.py`, M4.23/M4.24 section-2 grammar (partial), M5.4 EXP, M5.23 for the field layer.
  - Hints: the section-2 grammar is only partly decoded (M4.23 part b open), so compare at the level the writer round-trips today (node/link framing, coordinates) and mark the edge-attribute layer `UNKNOWN`; do not block the framing check on M4.24. A `_preserved` tile is a PASS only for the preservation property, never for "graph matches".
  - Done when: `tile_graph_roundtrip` reports PASS on the synthetic fixture and on the real splice, FAIL when one emitted link endpoint is moved, and `preserved` for an untouched tile; `python3 tools/selftest.py` passes; EXP states which attributes are compared and which are `UNKNOWN`.
  - Stop: if section 2 cannot be decoded for any edge (no grammar), report `BLOCKED — section-2 grammar unknown` naming M4.23/M4.24 and do not claim a graph check.
  - Falsifier: the check passes on a tile whose emitted graph has one fewer link, or a `_preserved` tile is reported as a graph match.
  - Claims: none yet

- [ ] **M5.38 — The card ladder P0–P4: what a Poland card contains at each step and which software gate it must pass**
  - Status: open · Owner: — · Critical: yes · Pair: solo
  - Depends: — (reads `reader-coverage.md`, `roadmap.md`, M3.17's copy/generate split)
  - Goal: "a Poland card" is five different things and the board mixes them. Fix the ladder so every M4/M5 task says which step it serves, and so the first step is as small as the formats we can already write.
  - Scope: one page, `docs/research/card-ladder.md`, and a `Step:` tag on each open M4/M5/M9 task block (one line each, nothing else edited). Proposed steps — P0: EU factory card with one tile whose section 1 holds OSM roads in a `0x2046` directory, everything else factory (M5.34/M5.29/M5.30); P1: all tiles of Dolnośląskie display-only (sections 2 and 4, `LEV3456R` and `REFER001` factory, so routing and search still answer with German data — stated as a known wrong behaviour, not hidden); P2: names (section 4, `LCTBL001`); P3: routing (section 2, `LEV3456R`); P4: search (`POINT`, `ADDRE`).
  - Input: `docs/research/reader-coverage.md` (30 rows: writer, reader, L3), `docs/research/roadmap.md`, EXP-2026-11-08-M3.17 (copy set), M5.35 (`mkpoland`).
  - Hints: for each step write three lists — files generated, files copied, and *inconsistencies the firmware will see* (a P1 card has roads in section 1 that section 2 does not know). For each inconsistency name the task that finds out, in emulation, what the firmware does with it (M9.44 for file-level, M4.40/M9.13 for tile-level). The gate of a step is the set of L1/L2 checks plus the L3 targets that exist for its generated files; a file with no L3 target is listed as `ungated`, in bold.
  - Done when: the page exists; every open M4/M5/M9 block carries `Step: P0…P4` or `Step: tooling`; the Priorities section orders by step; `todo_check.py` passes.
  - Stop: do not invent format facts to fill a cell — `unknown` with the task that answers it.
  - Claims: none yet

- [ ] **M5.39 — `l2check --tiles` accepts a bare cell name, matches 0 tiles and prints `RESULT: PASS`**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (`tools/l2check.py` is on `main`; no other task's block is needed)
  - Goal: C-3566 records the footgun without a task: every caller that writes `--tiles B48R058R` (M5.33's Precheck did, until QA 2026-11-17 fixed that line) gets `tiles=0` and `RESULT: PASS`, so a broken tile reads as a passing gate. This is the L2 signal M5.34/M5.30/M5.11 depend on, not a record repair.
  - Precheck: on the factory root `python3 tools/l2check.py --root /home/marek/projekty/leafre-work/m5.29-factory-root --partial --no-golden --no-cmp --tiles B48R058R` prints `[tile_roundtrip] OK (tiles=0; preserved=0)` and `RESULT: PASS`; the same command with `--tiles B48R058R.DAT` prints `tiles=1`.
  - Scope: `tools/l2check.py` only: a `--tiles`/`--semantic-tiles` value that names no file present on the card is a usage error (exit 2) or, under a new `--require-tiles`, a `FAIL`; a bare cell name (`B48R058R`) is named in the message with the `.DAT` form to use; a requested name that resolves to a file is unchanged. Do not change what the tile checks assert.
  - Input: `tools/l2check.py` (`--tiles`, `--semantic-tiles`, the `tiles=` count), C-3566, EXP-2026-11-17-M5.34-parcel (Follow-ups), M5.33's Precheck.
  - Done when: `python3 tools/l2check.py --root <factory-root> --partial --no-golden --no-cmp --tiles B48R058R` exits non-zero and names `B48R058R.DAT`; with `--tiles B48R058R.DAT` it still prints `tiles=1` and `RESULT: PASS`; `--selftest` covers both; `python3 tools/selftest.py --only l2check` and the L1/L2 CI job stay green with a fixture that needs no vendor data.
  - Stop: if the tile check cannot run without a vendor root, land only the name-vs-file rejection (exit 2) and record the vendor-root limitation; do not invent a fixture.
  - Claims: C-4290–C-4299

- [ ] **M5.40 — Card ladder P0 is only checked on this host: pin the M5.34 factory-backed run as a QA manual regression**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M5.34 (done), H84 (the `workflow_dispatch`/scheduled skeleton), M5.38 (the ladder page names P0)
  - Goal: M5.34's P0 step (`EXP-2026-11-17-M5.34-parcel`: 480 files compared, 2 differ, tile `293,990,518 B` / `b746427c…34c2ef`, `cardcheck` + targeted `l2check` rc=0) ran once by hand. Nothing on `main` fails when that run stops completing — CI has no factory tree and must not download one, so the regression today is invisible. One scheduled/manual job that reproduces the P0 gate (skip, not red, when the factory tree or OSM extract is absent) makes rule 17's "highest ladder step that passes its gate" a check, not a log line.
  - Precheck: `gh run list --workflow "CI quality gate"` shows no step that names `one_tile_pipeline --factory-root`; `grep -l 'one_tile_pipeline' .github/workflows/*.yml` prints nothing; on this host the EXP Reproduction block (its `--osm /home/marek/projekty/leafre-work/osm/dolnoslaskie-latest.osm.pbf`, or a rule-11 fetch) exits 0.
  - Scope: extend H84's workflow (or a second `workflow_dispatch`/scheduled file, name in PR) with a P0 job: resolve the factory tree and a Dolnośląskie extract from the runner cache or a rule-11 fetch, verify the factory tile SHA-256, run `python3.13 tools/one_tile_pipeline.py --factory-root … --cell B48R058R --parcel 76,940 --osm … --clip --out … --json …`, assert exit 0 and `counts.cardcheck_rc=0` with `tiles=1`, upload `report.json`; a missing input prints `SKIP (no factory tree/extract)` and is neither green-as-passed nor red. Never `pull_request`/`push`; no vendor bytes in the repo.
  - Input: EXP-2026-11-17-M5.34-parcel (Reproduction + Follow-ups), `.github/workflows/README.md`, H84's block, `tools/one_tile_pipeline.py` (`--factory-root`, `--parcel`, `--clip`, `report.json`), `tools/zlibinfo.py` (stock-zlib guard), `tools/fetch_image.py`.
  - Hints: reuse H84's exit-code policy — a missing input is exit 2/`SKIP`, not red. Assert `tiles=1` as well as exit 0 (C-3566: `tiles=0` is the footgun M5.39 closes). Record the interpreter and zlib build from `report.json`; a zlib-ng host is a skip with a reason, not a result (C-3569).
  - Done when: a `workflow_dispatch` run on a runner with both inputs completes the P0 gate and the summary names exit code, tile SHA-256/size, `cardcheck_rc`, `tiles=1` and the zlib build; with the factory tree absent it prints `SKIP (no factory tree)`; the workflow never triggers on `pull_request`/`push`; `.github/workflows/README.md` documents it; `python3 tools/selftest.py` unchanged.
  - Stop: if a runner cannot hold the 480-file factory tree and the ~90 MB extract within the job timeout, ship the skeleton with the explicit `SKIP` path and record the cache gap in the EXP; do not vendor either input.
  - Claims: C-4300–C-4309

- [ ] **M5.41 — One expected-change-set for the one-tile run: `changed_set_expected` and the gate disagree on `DRSTR001.DAT`**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: M5.34 (done — the run and the gate it reports)
  - Goal: `one_tile_pipeline.build_factory_out` writes `changed_set_expected = ["MAPAL001/<cell>.DAT"]` (`tools/one_tile_pipeline.py:1250`) while no other place defines what a correct run is allowed to change: the gate's manifest allowlist is a literal at `:1399` and is never exported, and the non-parcel path fills `changed_set` from `counts.rebuilt_files` (`:663`, `:1367`). On the M5.34 run the two disagree (`changed_set_expected` excludes `DRSTR001.DAT`, the file that does change and that the gate accepts), so a reader or a future card gate that trusts `expected` would read the correct run as wrong. Two definitions of one set in one module is the coupling defect; the fix is one function.
  - Precheck: `python3 -c "import json;d=json.load(open('/home/marek/projekty/leafre-work/m5.34/nav-report.json'));print(d['changed_set_expected'], [x['path'] for x in d['tree_diff']['differing_files']])"` prints `['MAPAL001/B48R058R.DAT']` against `['DRSTR001.DAT', 'MAPAL001/B48R058R.DAT']`.
  - Scope: `tools/one_tile_pipeline.py` only: one `expected_changes(cell, rebuilt)` helper (tile + rebuilt manifests from `counts.rebuilt_files`, deduplicated) used by `build_factory_out` and by `one_tile_gate`'s `manifests` argument; `report.json` keeps both `changed_set_expected` and `changed_set_actual` and the selftest asserts `expected ⊇ actual` on the fixture and that an out-only file still leaves `unexpected_differences` non-empty. No change to the gate's PASS conditions.
  - Input: `tools/one_tile_pipeline.py` (`:663`, `:1250`, `:1367`, `:1395-1410`, `one_tile_gate` at `:1119`), EXP-2026-11-17-M5.34-parcel (`tree_diff`), C-3563.
  - Hints: do not fold `MMAIN001.DAT`/`CMP.LST` in unconditionally — the M5.34 run re-emits them byte-identically and they are *allowed*, not *expected*; keep "allowed" and "expected" as two sets if the export needs both.
  - Done when: on the M5.34 factory run `changed_set_expected` equals `{MAPAL001/B48R058R.DAT, DRSTR001.DAT}` and still satisfies `expected ⊇ actual`; `python3 tools/one_tile_pipeline.py --selftest` passes and covers (a) a report whose actual set is the expected set, (b) an extra out-only file (B2) still FAILs, (c) a run that changes only the tile leaves `DRSTR001.DAT` out of `actual` without failing `expected ⊇ actual`.
  - Stop: if a second caller depends on `changed_set_expected` meaning exactly one path, name it in the EXP and keep both keys (`changed_set_tile`, `changed_set_expected`); do not delete a field another task's Done-when cites.
  - Falsifier: a fixture where `actual` is a strict subset of `expected` still reports `tile_plus_manifests_only: false`, or a gate PASS survives an unexpected file.
  - Claims: none yet

- [ ] **M5.42 — Records overtaken by a later merge: a TEMPLATE section, plus four concrete corrections**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (all four records are merged; this is text)
  - Goal: a record that a later commit overtook still reads as current, and `claims_check` cannot see prose. Four instances from the 24h window, each with the file it lives in: (1) `docs/research/claims.md` C-1240 ends "so M8.A2 stays `blocked`" although #217 closed it (the row's own status column already says `BLOCKED (done-when access-list clause)` and the clause was withdrawn); (2) `docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` Status bullet says "Task status is `blocked`, not `done`" and its own §Verdict line says the same; (3) the same EXP's **Status** header (lines 5-7) and its `Notes left for the navigator` last bullet repeat it; (4) C-3563 and C-3564 say `DRSTR001.DAT` changed because "the tile's on-disk size changed" — the measured diff is 7 bytes: the `MAPAL001` directory entry's `value` word (`0xd1e00400 → 0xd2274b76`, +0x474776 = the +4,671,350 B appended tail, i.e. the new structure offset) *and* the `B48R058R.DAT` entry's size word (`0x113ea900 → 0x1185f076`), i.e. offset **and** size, so the reader learns where the new tail starts as well as how big the tile is.
  - Precheck: `grep -n 'M8.A2 stays' docs/research/claims.md` and `grep -n 'Task status is .blocked' docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` each print a line; `cmp -l ~/projekty/leafre-work/m5.29-factory-root/DRSTR001.DAT ~/projekty/leafre-work/m5.34/nav-out/DRSTR001.DAT | wc -l` prints `7`.
  - Scope: `docs/experiments/TEMPLATE.md` gains one section, **"Overtaken by a later commit"** — a bullet list `claim/EXP line | overtaking commit | what it now reads as`, required whenever a later merge changes a status, a count or a limit the record cites, with the same "quote the command" rule as everywhere else; the four corrections above as edits in place (C-1240, the M8.A2 Status/Verdict/navigator note, C-3563, C-3564) each naming the overtaking commit (`280cd74`, `f5df583`). No new claim rows, no number changes beyond the two measured byte offsets.
  - Input: `docs/research/claims.md` C-1240/C-3563/C-3564, `docs/experiments/EXP-2026-11-17-M8.A2-machine-skeleton-reprobe.md` (Status, Verdict, Notes), EXP-2026-11-17-M5.34-parcel §Observations `tree_diff` block, `git log -1 280cd74`, `docs/experiments/TEMPLATE.md`.
  - Hints: keep "observations" and "corrections" apart in the M8.A2 EXP — the Status header is metadata, the §Verdict row is the evidence table; edit both to the same sentence. Do not re-run anything; every number in the four edits is already in the EXP or in the command above.
  - Done when: the TEMPLATE has the new section and `python3 tools/claims_check.py --strict --count-check` still prints `0 mismatches`; `grep -c 'M8.A2 stays' docs/research/claims.md` prints `0`; the M8.A2 EXP Status and Verdict say `done` with the `280cd74` merge named; C-3563/C-3564 name the 7 bytes (size word + offset word) instead of "the on-disk size"; `python3 tools/todo_check.py` passes.
  - Stop: if a correction would change a VERIFIED claim's meaning (not just its stale tail), stop and write a `Supersedes:` row instead of editing — that is a new claim, not a correction.
  - Falsifier: a record still says `blocked`/`stays blocked` for M8.A2, or C-3563 still attributes both changed words to the size alone.
  - Claims: none yet

- [x] **M5.43 — `build.sh --check-version` reports a verdict, not a traceback**
  - Status: done · Owner: task/m5.43-check-version-verdict · Critical: no · Pair: required
  - Depends: M8.A10 (done — the probe and its `QEMU_PINS` table)
  - Goal: the probe's purpose is a per-patch verdict for a release that may not have a pin; a FAILED patch is its normal answer. Today the 11.1.3 probe prints the correct table, then a second note, and exits `1` (the full build's generic failure code; no traceback), so a caller (M8.A9, a future bump) cannot tell "probe says 3/2" from "the probe broke", and any wrapper that treats rc 1 as a crash will read the answer as a tool failure.
  - Precheck: `bash tools/qemu-ze0/build.sh --check-version 11.1.3` prints `3 applied, 2 failed, 1 unpinned-tarball`, then the port-delta note, and ends with rc `1`; `bash tools/qemu-ze0/build.sh --selftest` is 56/56.
  - Scope: `tools/qemu-ze0/build.sh` only: `--check-version` keeps the extraction, the `patch --dry-run` table and the one-line verdict, and exits with a defined code — `0` all patches apply, `4` at least one patch fails to apply (a porting delta), `2` usage, `3` missing input/download fault — printing the verdict line last and nothing after it; `--selftest` gains a red case (an injected patch that must fail) and a green one, both without a network build. `README.md` gets the exit-code table.
  - Input: `tools/qemu-ze0/build.sh` (`--check-version`, `QEMU_PINS`, the `st_ok`/`st_fail` helpers), EXP-2026-11-17-M8.A10-bump-8210 (the 3/2 table), `docs/research/qemu-ze0-port-delta.md` (M8.A9 consumes the verdict), `tools/qemu-ze0/README.md`.
  - Hints: the failure is in the check path's cleanup or hash step, not in `patch`; reproduce with `bash -x` once and record the line in the EXP. Do not make a FAILED patch an exit 0 — M8.A9 needs the signal.
  - Done when: `bash tools/qemu-ze0/build.sh --check-version 11.1.3` prints the 3/2 table and exits `4` with no traceback; `--check-version 8.2.10` exits `0` (5/5); `bash tools/qemu-ze0/build.sh --selftest` passes with both outcomes and `python3 tools/selftest.py` stays green (`--only qemu` exits 2 — not a discovered suite, see C-4424).
  - Stop: if the failure is inside the pinned tarball's own patch tool rather than the script, record the line and the tool version and exit 4 with the reason — the code path is still the script's.
  - Falsifier: a probe where some patches fail exits 0, or one where all apply exits non-zero.
  - Result: `--check-version 11.1.3` → `3 applied, 2 failed` + rc `4`; `--check-version 8.2.10` → `5 applied, 0 failed` + rc `0`; truncated pinned tarball via `--srcdir` → `has 13 bytes, expected 132685948` + rc `3` — `docs/experiments/EXP-2026-11-18-M5.43-check-version.md`
  - Claims: C-4420–C-4424

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

- [x] **M5.45 — Tile-writer idempotence and size budget: the same input twice must give the same bytes**
  - Status: done · Owner: task/m5.45-tilewriter-idempotence · Critical: no · Pair: required
  - Depends: M5.34 (done — the run that showed the growth), M5.4 (the 18-parcel run it compares to)
  - Goal: `splice_factory` writes a grown slot block by *appending* it and repointing the slot (`tools/tilewriter.py:927-935`, `clarion_tile.pad256`), so tile size is a monotone function of how many times a directory is spliced, not of the content: the M5.34 tile is +4,671,350 B over factory and its hypothesis is "the appended slot blocks for the parcels written". No test runs the same input twice, and nothing counts the bytes a *second* map update of the same directory adds — the failure mode the card's own M7.1 size budget inherits. A tile that grows on every rebuild cannot be shipped as one-variable cards, and a non-idempotent writer makes every diff larger than the change it carries.
  - Precheck: `python3 tools/tilewriter.py --selftest` passes and `grep -c 'superseded_bytes' tools/tilewriter.py` is `3` (the field is reported but never asserted); the M5.34 `report.json` `counts.tilewriter_stdout` carries `container.appended`; run the same `--parcel 76,940` build twice into two out dirs and `cmp` the tiles (the second pass needs a *fresh extract of the factory tile*, so this is the test to add, not a command that exists).
  - Scope: `tools/tilewriter.py` (one in-place/dedupe pass, name chosen in the PR, that writes a rebuilt slot block **in place** when it fits and refuses to append when the previous block of the same slot is identical) plus `tools/one_tile_pipeline.py` (`--selftest` case), `docs/format/map-tiles.md` (one paragraph: append semantics and the size consequence), and one measured number in the EXP: tile bytes after 1, 2, 3 splices of the same directory with the same input. No change to the record grammar or to the gate.
  - Input: `tools/tilewriter.py` (`splice_factory` `:819-940`, `pad256` `:929`, `superseded_bytes`), `tools/ze0-viewer/tools_ze0/clarion_tile.py` (`pad256`, `block_bytes`), EXP-2026-11-17-M5.34-parcel (§Observations tile_diff, the +4,671,350 B), M7.1 (the budget this feeds).
  - Hints: the second run must start from the *factory* tile and produce the same bytes as the first (determinism), and the *update* case must start from the generated tile and produce a bounded delta — say which of the two the task measured. `pad256` aligns to 256 B, so a tail of zeros is expected; the assertion is about the appended block, not about padding.
  - Done when: `one_tile_pipeline --selftest` contains a case where the same input built twice yields byte-identical tiles (determinism), and a case where a second splice over an already-spliced directory is bounded (the delta is recorded, not unbounded); `docs/format/map-tiles.md` states the append rule and the measured 1/2/3-splice sizes are in the EXP; `python3 tools/tilewriter.py --selftest` green.
  - Stop: if the container cannot rewrite a slot in place without moving the block (the shared-block case M5.4 found), record that case and make the *bounded* claim only for owned slots; do not claim in-place for blocks the reader shares.
  - Falsifier: two runs of the same input produce different tile bytes, or the second splice grows the tile by the first splice's superseded bytes again.
  - Claims: C-4460–C-4469
  - Result: EXP `docs/experiments/EXP-2026-11-18-M5.45-idempotence.md`. Full clipped corpus (907,969 nodes / 112,965 ways, 1,024 parcels): factory 289,319,168 -> 293,990,518 -> 293,990,518 -> 293,990,518 B (+4,671,350 B once, +0 B after; A0..A3 byte-identical, SHA-256 `b746427c…34c2ef`); the append-always mutant grows the second splice to 298,662,006 B (+4,671,488; `tilewriter --selftest` 69/73, `one_tile_pipeline --selftest` 3 FAIL); the (72,936) level-2 refusal is **physical aliasing** of the level-2 container at [5120,21644) by 9 level-1 preserve-only parsed spans (6 slots start at 5120), not a shared record key — the bounded claim covers level-1 owned slots only; the level-2 cause (parser phantom vs real write) is left to the Follow-up.

- [x] **M5.46 — P1 first slice: the profile-to-tile containment census (how many tiles a Dolnośląskie card needs, and which are whole)**
  - Status: done · Owner: task/m5.46-p1-containment-census · Critical: yes · Pair: required
  - Depends: — (the factory tile list and `mesh_grid.py` are on `main`; no write, no OSM extract)
  - Goal: **M5.38** (open) defines P1 as "all tiles of Dolnośląskie display-only", but `profiles/dolnoslaskie-test.json` pins exactly one tile (`include: ["B48R058R"]`, `max_tiles: 1`) and no block answers how many `MAPAL001` tiles the region's 14.0–17.9 E × 49.9–51.9 N box intersects or contains. Without that census the P0 card cannot be extended to P1 and the scale of the rest of the ladder is a guess. This is the rule-17 first slice: enumerate, no splice.
  - Precheck: `python3 tools/mesh_grid.py list <factory MAPAL001>` prints 45 tiles and `cell B48R058R` prints `48.00.. 53.33 N 12.00.. 20.00 E`; a bbox-intersection over those 45 rows is the census (no vendor bytes are read beyond tile names; `profiles/dolnoslaskie-test.json` is the box).
  - Scope: `tools/parcel_census.py` or `mesh_grid.py` gains one subcommand (name in the PR, e.g. `mesh_grid.py cover PROFILE_DIR`) that reads a profile's `region.bbox` and prints, per tile: lat/lon box, `intersects`/`contained`/`outside`, and the profile's `include` list; plus one paragraph in `docs/research/card-ladder.md` (or M5.38's page once it exists) stating P1's tile count and how many are whole (the rest are edge tiles the profile's `border_buffer_deg` decides). No tile is written; no OSM data is read. If M5.38 has not landed the page, put the paragraph in `profiles/README.md` and cross-link.
  - Input: `profiles/dolnoslaskie-test.json` (`region.bbox`, `tiles`, `limits`), `profiles/poland-full.json`, `tools/mesh_grid.py` (`list`, `tile_box`), the factory `MAPAL001` directory, M5.38's block.
  - Hints: the 45 `.DAT` names are the tile universe; a tile is `contained` when the profile's region box lies inside the tile box (the tile covers the whole region, a P1 copy-whole candidate); it is `intersects` when it only overlaps the region box widened by `border_buffer_deg`. At P1 every non-factory tile is a fresh splice and every factory one is either copied verbatim or spliced — say which in the census, because the P1 card's file count is what M7.1's size budget multiplies. Positive control: the bbox must select `B48R058R` (the P0 tile) and no other tile as contained; negative: a box moved into the Atlantic selects nothing.
  - Done when: the new subcommand prints one row per tile with its class and the profile's include list, `--selftest` covers a contained tile, an edge tile and an empty box; the repeated census on `profiles/dolnoslaskie-test.json` prints `contained=1` (`B48R058R`) and the page states P1's tile count; `python3 tools/selftest.py --only mesh_grid` (or the chosen tool) green.
  - Stop: if a profile has no `region.bbox`, report the missing field and the profile's `tiles.include` only — do not invent a box (that would be the P1 guess this task removes).
  - Falsifier: the census selects a tile whose `mesh_grid.py cell` box does not touch the profile bbox, or reports P0's tile as anything but `contained`.
  - Pair: required
  - Result: EXP-2026-11-18-M5.46-containment. `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json <MAPAL001>` prints `census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45` (B48R058R the sole contained tile, so P1 is one factory tile copied verbatim); `cover profiles/poland-full.json` prints `contained=0 intersects=4 outside=59`; `--all` prints all 63 lattice rows; `mesh_grid --selftest` OK (16 ok). The task's Hints had the containment test inverted; the Done-when's contained=1 settles the direction (region inside tile). Claims C-4470–C-4475.
  - Claims: C-4470–C-4479


- [ ] **M5.47 — M5.30's fit census: does one changed tile fit an existing cluster chain before anyone writes it?**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M5.29 (done — the changed tile and rebuilt manifests), M5.45 (done — the append/in-place/unchanged semantics the fit question needs)
  - Goal: M5.30 is the last P0 rung and its `Stop:` is "if changed tile/manifests cannot fit existing chains and relocate/reconcile widens diff beyond changed files, record ranges and stop". Nobody can tell whether that stop fires until a writing run exists, so the cheap half is a census: for the M5.34 result tile and the manifests it rebuilds, does the new byte length fit the FAT cluster chain `imgpatch` would reuse, and if not, by how much and which file. No write, no image copy. This is the rule-17 first slice of M5.30.
  - Precheck: `python3 tools/imgpatch.py --selftest` passes; the M5.34 report names the changed tile and the rebuilt manifests (`~/projekty/leafre-work/m5.34/report.json`); `python3 tools/cardcheck.py --selftest` passes.
  - Scope: one subcommand (name in the PR) on `tools/imgpatch.py` or a new `tools/fit_census.py` that, given a card image and a generated tree, prints per file: factory on-disk bytes, generated bytes, delta, cluster chain slack, `fits` / `needs_relocation`. Reads the image; writes nothing. Reuses the M5.34 output tree as the input, plus one synthetic over-budget case.
  - Input: EXP-2026-11-17-M5.34-parcel (`tile_diff`, `tree_diff`), EXP-2026-11-18-M5.45-idempotence (append/in-place semantics), M5.29's rebuilt manifests, `tools/imgpatch.py` (chain walk), `tools/cardcheck.py`.
  - Hints: the tile grew +138,994 B at level 2 and +4,671,350 B at level 1; the first question is the level-1 figure against the factory chain slack, because that is the run M5.34 actually made. A file with slack >= delta is a one-variable card; report the smallest slack in the tree so M5.30 knows if it is a one-file or an all-files problem.
  - Done when: the census prints per-file `fits`/`needs_relocation` with the slack and delta, for the real M5.34 tree and for one synthetic over-budget file (control); a `--selftest` on synthetic FAT data covers fit, exact fit and over-budget; `python3 tools/selftest.py` green.
  - Stop: if the answer needs a real image copy to be trusted (FAT quirks), deliver the census on the real image and hand the write to M5.30 rather than copying images here.
  - Falsifier: the census reports `fits` for a file whose delta exceeds its chain slack, or a synthetic over-budget file with spare slack is reported `needs_relocation`.
  - Claims: C-4560–C-4569

- [ ] **M5.48 — `tilewriter` leaves a partial `--out` tree when the build fails, so a failed run looks like a card**
  - Status: open · Owner: — · Critical: no · Pair: solo
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

## M6 — L5 bench/car: hardware and safety

No hardware is available now (L5). Planning tasks are open; tests wait. L4 (full-system emulator, M8) is the software integration path to prepare before L5.

- [ ] **M6.13 — Prepare the S3 bench package manifest (no hardware, no vendor bytes in repo)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M5.14 (S3 done), M5.24 (diff proof), M9.31 (runnable L3 evidence)
  - Pair: solo
  - Goal: make the S3 (LEV3456) bench run cheap when hardware returns: record artifact SHA-256/size/diff ranges, how it differs from S0/S1/S2 (one variable), which offline/L3 gates passed, and S3 pass/fail criteria. Image stays outside repo.
  - Precheck: `docs/research/card-test-plan.md` defines S3 criteria; M5.14/M5.24 EXPs name image/diff-ranges or package records `UNRECORDED`; `todo_check.py`/`claims_check.py` pass.
  - Scope: `docs/research/bench-packages/s3.md` (or a defined section in `bench-evidence-pack.md`) with manifest fields and reproducible hash/size verification commands outside repo. No flashing, no L5 claims.
  - Input: M5.14 EXP, M5.24 diff proof, M6.3/M6.7 plan, M9.31 runnable L3 evidence (or `l3check`/`progress_report` output).
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

- [x] **M8.A2 — Machine skeleton** `hw/sh4/ze0.c`: `sh7785`, RAM at phys
  `0x08000000` (128 MiB), P1/P2 aliases, unimplemented-device catch-all over
  `0xff800000`–`0xffffffff` and areas 4/6, `select SH4_CCN` with
  `sh4_ccn_iomem()` at `0xff000000` and `sh4_ccn_arrays()` at `0xf0000000`,
  and one `ze0-stubs` instance.
  - Status: done · Owner: task/m8.a2-reprobe · Critical: yes
  - Re-probe (2026-11-17): `build.sh --force --jobs 8` applies all five
    sorted patches on pristine 8.2.7, builds `qemu-system-sh4` and `-M help`
    lists `ze0` (C-4310). `-M ze0` boots `archive/head256.img` the full 10 s
    wall clock with `exceptions: 0` and one unmodelled access, `write 0x38`
    (C-4311). The patch shipped with two bugs, each fixed and each reproduced
    by its own negative control: a second `ze0.ram` block beside
    `default_ram_id` (`RAMBlock "ze0.ram" already registered, abort!`) and
    `config ZE0` without `UNIMP` (`unknown type 'unimplemented-device'`).
    The old access-list clause is **withdrawn as a board defect**, not failed:
    a machine that maps `sh4-ccn` at `0xff000000` cannot emit the `-M none`
    invalid list, and it already differs with the same `run.sh` extents
    (1 vs 8, C-4312), so the clause contradicted the task's own purpose.
    The exempted `final pc`/"2 854 passes" numbers were **samples**, not
    results (`run.sh:542-548` polls HMP on a wall clock; 6 ze0 runs gave 6
    PCs); the record now carries only the stable observables plus a
    repeat-run table.
  - Depends: — (M8.A1, M8.A4 and M8.A5 are merged)
  - Note (PM 2026-11-06): the three series were never built together. M8.A1 saw
    `m8a4-0002/0003` rejected on 8.2.7; M8.A4/M8.A5 report them applying (the
    0003 banner says "Base: QEMU 8.2.7"). Settled: one clean
    `build.sh --force` over `patches/*.patch` applies all five in `LC_ALL=C`
    order (C-4310).
  - Note (2026-11-17, former blocker): the `write 0x38` null store on the
    declared-length load (`nk.exe 0x8802ec46`, `r2 = 0`) and the
    `0x040 [tlb_miss] pc=0x00005bd0` chain on the probe's full extents are
    follow-ups for **M8.A3** (loader/root cause), not gates of this task.
    The oracle is version-sensitive: `ce_qemu_probe.py` must be given
    `--qemu <8.2.7 build>` (PATH is 11.1.3, which yields 0 accesses).
  - Done when: `bash tools/qemu-ze0/build.sh --force` applies every patch,
    builds, and `qemu-system-sh4 -M help` lists `ze0`; `-M ze0` boots
    `archive/head256.img` for ≥10 s wall clock with 0 CPU exceptions and a
    stable access list (1 unmodelled access, `write 0x38`); that residual
    store is attributed to a named instruction; the run log and the final
    patch order are in the EXP. (The earlier clause "`-M ze0` reproduces the
    `ce_qemu_probe.py` access list" is withdrawn: see C-4312.)
  - Result: EXP-2026-11-17-M8.A2-machine-skeleton-reprobe (C-4310 build,
    C-4311 boot, C-4312 machine-vs-extent; C-1240 corrected). Patch:
    `tools/qemu-ze0/patches/ze0-0001-hw-sh4-ze0-machine.patch`
    (SHA-256 `59a47b7f…a9792`).
  - Claims: C-1240–C-1249

- [ ] **M8.A3 — Built-in loader** (`kernel=0x3e00200`, `app=0x200200`):
  parse `ECEC`/`ROMHDR`, copy B/C and A to `physfirst & 0x1fffffff`, PC =
  `nk.exe` entry. Done when booting needs no `-device loader`.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.A2
  - Claims: C-1250–C-1259
- [x] **M8.A10 — Bump the QEMU pin 8.2.7 → 8.2.10**
  The pin is 8.2.7 (2024-09-18) while 8.2.10 (2025-03-26) is the last release
  of the same branch and the whole series applies to it unchanged. Move the
  pin, make the hash table per-version, and add `--check-version` so the next
  bump is a probe rather than a heroic edit.
  - Status: done · Owner: task/m8.a10-bump-qemu-8210 · Critical: no
  - Depends: — (M8.A2 merged)
  - Goal: the default build is 8.2.10 and an unpinned version can be probed
    without being built.
  - Precheck: `diff -r` of `hw/sh4`, `configs/devices/sh4-softmmu` and
    `include/hw/sh4` between 8.2.7 and 8.2.10 must be empty, and all five
    patches must apply to pristine 8.2.10 without an edit. Both measured:
    trees byte-identical, 5/5 apply (C-4330).
  - Scope: `QEMU_PINS` table (8.2.7 kept, 8.2.10 default), a full build that
    refuses an unpinned version, `--check-version V` that verifies/extracts/
    applies/reports and builds nothing, README pin table and the "8.2 LTS"
    wording (8.2 is EOL), `--selftest` coverage for the table and the probe.
  - Done when: `build.sh --force` builds 8.2.10, `-M help` lists `ze0`, and
    `-M ze0` boots `archive/head256.img` with the same stable observables as
    the 8.2.7 build (0 exceptions, one `write 0x38`); `--selftest` passes;
    `--check-version 11.1.3` prints a per-patch verdict without building.
  - Stop: if any patch needs an edit for 8.2.10, that is a porting delta, not
    a bump — stop, keep the 8.2.7 pin, and record it as input for M8.A9.
  - Result: EXP-2026-11-17-M8.A10-bump-8210 (C-4330).
  - Claims: C-4330–C-4339

- [ ] **M8.A9 — Port the `ze0` patch series to current QEMU (11.1.3)**
  The five patches in `tools/qemu-ze0/patches/` are pinned to 8.2.7. Port the
  **intent** of each patch, not its diff: the per-hunk intent tables are in
  `tools/qemu-ze0/patches/README.md` §§1–6 and the measured delta is
  [`docs/research/qemu-ze0-port-delta.md`](docs/research/qemu-ze0-port-delta.md).
  - Status: open · Owner: — · Critical: no
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


- [ ] **M8.A6 — Debug serial** (`sh_serial` at `0xffe46000`; writer
  `0x8804cfa4`, pointer at `0x8804ce78`). Done when the CE boot banner
  appears or an EXP shows why not.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.A2
  - Claims: C-1280–C-1289
- [ ] **M8.A8 — F0 EXP + register table** in `docs/format/firmware.md`.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.A3, M8.A6 (M8.A4/M8.A5 merged, archived 2026-11-06)
  - Claims: C-1300–C-1309
- [ ] **M8.B1 — INTC model** (`0xff802000…`, `0xff804000…`, from
  `OEMInterrupt*` and the ISR at `VBR+0x600`). Done when a TMU0 interrupt is
  delivered and acknowledged.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.A2
  - Claims: C-1310–C-1319
- [ ] **M8.B2 — TMU** (`0xffd80000`, `0xffd81000`, `hw/timer/sh_timer.c`).
  Done when `CurMSec` advances.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.B1
  - Claims: C-1320–C-1329
- [ ] **M8.B3 — RTC/time** (`OEMGetRealTime`).
  - Status: open · Owner: — · Critical: no
  - Depends: M8.A2
  - Claims: C-1330–C-1339
- [ ] **M8.B5 — Milestone F1**: `filesys.exe` and `device.exe` start, 60 s
  without a fault.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.B1, M8.B2
  - Claims: C-1350–C-1359
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
- [ ] **M8.D1 — Decision gate after F1: continue to F2/F3?**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (trigger: M8 F1 stable kernel; see `todo-history-2026-11-05.md` §M8.D)
  - Goal: after F1, continue to F2/F3 only if L3 (M9) is blocked by runtime state, or an automatic regression loop without hardware is wanted; re-estimate F2–F4 and record the decision.
  - Done when: the decision and its re-estimate are written down; no code change implied.
  - Claims: C-1590–C-1594
- [ ] **M8.D2 — Decision gate after F3: go to F4?**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: — (trigger: M8 F3 SD mounted; see `todo-history-2026-11-05.md` §M8.D)
  - Goal: after F3, go to F4 only if the micon/CAN handshake (M8.C4/C5) looks scriptable; F5 stays out of scope unless M8.C19 shows a simple frame-buffer path.
  - Done when: the decision is written down; no code change implied.
  - Claims: C-1595–C-1599
- [ ] **M8.E1 — Run the kernel's ROM decompressor as a tool**
  - Status: blocked · Owner: task/m8.e1-run-rom-decompressor-retry (retry 2026-11-08) · Critical: no
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

- [x] **M8.E1c — QEMU slice for nk.exe decompressor oracle (compatible SH-4 map, DECOMP_SECT, EXP-49)**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (needs `qemu-system-sh4` LE with compatible memory map/`-M ze0` build deps or container; M8.A2 host deps may be missing)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M8.E1b, M1.2g (M8.A2 unblocks `-M ze0`; a documented compatible-map fallback may proceed in parallel)
  - Goal: execute a verified decompressor slice under QEMU and emit `decomp_oracle`-compatible results, so M1.2f gets runtime evidence (decoded length/hash for EXP-49, then Navi.exe sec1/sec2) without guessing the CE-LZXD block codec.
  - Precheck: `python3 tools/cedecomp_run.py --selftest` and `python3 tools/decomp_oracle.py --selftest` pass; `qemu-system-sh4` (LE) available and version recorded; IMG256 present/verified (rule 11). Record whether `-M ze0` is available or a compatible map is used (stock QEMU 11.1.3 `-M none` fails P1 0x88/0x8c access for nk.exe VAs).
  - Scope: `tools/cedecomp_run.py`/small helpers to run `probe` and `exp49` for `DECOMP_SECT 0x88037464` (preferred, C-2293) with a constructed input frame and minimal kernel-context/heap stubs sufficient for the section-decode path; output hashed decoded bytes as `decomp_oracle` JSON (no vendor bytes committed). Excludes full nk boot, F1, and 245/245 claims until produced.
  - Input: M8.E1b VAs (`DECOMP_WRAP/SECT/BLK/ALLOC`), `cedecomp.py`, EXP-49 vectors (`decomp_oracle.py`), `tools/qemu-ze0/` (`-M ze0` when built), `tools/ce_qemu_probe.py` patterns.
  - Done when: `cedecomp_run.py exp49 --image IMG256 --entry 0x88037464 --json <out>` (or documented equivalent) produces `decomp_oracle verify` PASS for EXP-49 sec1 (`0x484`) and sec2 (`0xcc0`) with recorded decoded SHA-256s in the EXP; `probe` still passes; negative control: wrong entry/garbled buffer does not verify.
  - Stop: if DECOMP_SECT requires kernel/global state not stubbable without F1/registry context, record faulting PC/register state and reduce scope to DECOMP_BLK sub-fragment under M9.29 or a narrower hook, with a follow-up; do not guess decoded bytes.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3260–C-3269

- [ ] **M8.E2 — Registry as loaded** (`boot.hv`, `default.hv`, `user.hv`):
  driver list, `IoBase`, `Irq`, load order. Two routes: static hive parser
  after M1.4, or a RAM dump after M8.B5. Done when the driver table is in
  `firmware.md`.
  - Status: open · Owner: — · Critical: no
  - Depends: M1.4, M8.B5 (either route: static hive parser or RAM dump)
  - Claims: C-1610–C-1619
- [ ] **M8.E3 — Dump loaded process images** (`Navi.exe` + DLLs after init)
  for L3.
  - Status: open · Owner: — · Critical: no
  - Depends: M8.E4
  - Claims: C-1620–C-1629
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

- [ ] **M9.2 — Ghidra project builder**
  - Status: open · Owner: — · Critical: yes · **Runner: non-Claude** (Ghidra
  - Note (H101, 2026-11-17): **runnable on Marek's host** (the agents run there; only the Claude sandbox lacks Ghidra). A decompiler is the largest single speed-up available for M3.26, M4.40 and every reader task: with `pdata` the function boundaries are exact, so import `Navi.exe` sec0 at `0x00011000` (SH-4 **little-endian**), create functions from `pdata.py table --json`, name imports from `cerom.py imports`, and export one `.c` file per function of the file layer (`0x00417d00…0x0041cab0`) and of the two 48-function tile subtrees into `archive/work/` (vendor-derived: never committed).
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

- [x] **M9.11 — L3: the firmware's chunk decoder on our recompressed `.cmp` (software S1)**
  - Status: done · Owner: task/m9.11-cmp-ind-reader-closeout · Critical: yes · Pair: pair
  - Result: EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md (reconciles EXP-2026-11-08-M9.11-chunk-decoder.md / M9.11b). `chunk_decoder_l3.py` and `runner.py cmp_ind_reader` (`firmware_call`, declared sec1 `inflate_mask[17]` at `0x574de0`, provenance explicit, no silent default) return page `0x840ba0` byte-identical to `cmpind.decode` for factory/S1/S2 POINT010 pairs; `--mutate corrupt-ind` rejected (`r0=-1`); `--mutate swap-4-8` fails cleanly (`r0=65536`). `cmp_ind_reader` registered in `targets.json` (M9.11b). Sec1-byte equality remains HYPOTHESIS (M1.2f). L3 fragment scope (chunk decode), not full `.ind` parser/opener or M9.12 `l3check --card` corpus acceptance.
  - Note (rule 15, 2026-11-09 PO): M9.11b done (firmware-call entry kind); re-opened then closeout-verified 2026-11-09. Prior blocker resolved: registration filled by M9.11b; sec1 inflate table (`0x574de0`, `inflate_mask[17]`) provenance explicit/declared, no silent default; sec1 bytes not read from decompressed sec1 (M1.2f open).
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
  - Status: open · Owner: — · Critical: yes
  - Note (H51, 2026-11-11): re-run after H51 before anything else (**M9.36**): the `UNMAPPED 0xfffffec6` stop of M9.35 has the shape of the engine defect fixed in H51 (`mov.w R0,@(disp,Rn)` stored through `r0`) — HYPOTHESIS until re-run. `0x00419350` is a pdata `START` (length `0x334`, ends exactly at `0x00419684`).
  - Note (Rule 15, M9.35 done): load-model blocker removed by M9.35 (zero BSS + bound IAT + INIT guard). Prior blocked/re-open notes kept below. M9.35 IMG256 scratch probe of `sub_00419350` (EXP-2026-11-10-M9.35-sec1-load-model) gets past `0x0055d8fc` and stops at `UNMAPPED 0xfffffec6..0xfffffec8` (empty-args/context probe); rerun with proper context, M9.24 import/file stubs and M5.6 rebuilt DRSTR as needed for verdict.
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
    blocked on M1.2f/M9.24/M5.6 as applicable (do not guess verdicts). If a probe stops at `INIT 0x… (M1.2f)`, only that address needs M1.2f.
  - Claims: C-2240–C-2249
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
  - Status: open · Owner: — · Critical: no
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


- [ ] **M9.24 — Module entries that call coredll file APIs: bind imports, stub the CRT file calls**
  - Status: open · Owner: — · Critical: yes
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

- [x] **M9.29 — Ghidra headless micro-harness for decompressor sub-fragments (LE SH-4)**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (Ghidra 12.2+/JDK required; in-repo script/selftest runnable without Ghidra)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M1.2g, M8.E1b (M9.2 project import helps but is not required for a targeted function run)
  - Goal: test `DECOMP_SECT`/`DECOMP_BLK` and helper sub-fragments on controlled buffers in Ghidra headless/pyghidra, emitting `decomp_oracle`-compatible results. Complements QEMU (M8.E1c) and isolates CE-LZXD block-codec behavior.
  - Precheck: `python3 tools/decomp_oracle.py --selftest` passes; harness script has `--selftest`/`--plan` with no Ghidra/vendor data. With Ghidra: `analyzeHeadless` found and processor is **SH-4 little-endian** (not BE) per M1.11/M8.E1b/C-2290; `ghidra_import.py`/`l3_run.py` BE references are a hazard to fix/guard.
  - Scope: script under `tools/l3_harness/ghidra/` (name in PR) to load nk.exe image B at base, map src/dest/stack, call chosen VA (DECOMP_SECT/BLK/helper) with r4-r7/stack per prototype, read dest/len/r0, write JSON for `decomp_oracle verify`. No full-reader wiring, no 245-section claim without evidence, no default PR CI.
  - Input: M8.E1b VAs, IMG256 nk.exe mapping via `cerom.py`, `decomp_oracle.py`, `ghidra_import.py` patterns (LE-corrected).
  - Done when: `--plan` prints headless command/processor/VA/memory/expected output; `--selftest` validates plan/result shape without Ghidra; with Ghidra (EXP, non-Claude) EXP-49 sec1 or a pinned DECOMP_BLK sub-fragment yields `decomp_oracle verify` PASS or a faulting-PC negative EXP localizing the codec gap.
  - Stop: if controlled-memory execution is not feasible in the available Ghidra version, record limitation and use Ghidra decompilation/disassembly as evidence feeding M1.2f (not runtime proof) with a follow-up.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3150–C-3159

- [x] **M9.30 — DECOMP_BLK sub-fragment map and test vectors (shift/LZXD-like, feeds M1.2f)**
  - Status: done · Owner: — · Critical: no
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M8.E1b, M1.2g (M9.29 and M8.E1c provide runtime oracles when available)
  - Goal: break `DECOMP_BLK 0x8803a384` / `DECOMP_SECT 0x88037464` into testable sub-fragments (bit reader, shifts/masks, E8/`0x8d80805b` block handling, length/distance decode) with pinned inputs/expected outputs, so `sh4dis.py` shift-encoding gaps and the CE-LZXD codec are resolved against evidence.
  - Precheck: `python3 tools/sh4dis.py IMG256 nk.exe --image-start 0x3e00200 --va 0x8803a384 --count 20` (or helper VAs) decodes as far as supported; `python3 tools/decomp_oracle.py --selftest` passes. IMG256 per rule 11.
  - Scope: analysis + small committed test-vector fixtures (hex/JSON, no vendor blobs beyond short bytes/hashes/offsets) and `sh4dis.py`/helper extensions for blocking shift encodings (SHAD/SHLD/rotcl etc.) with selftests; runtime sub-fragment results from M8.E1c/M9.29 when run. No guessed full codec.
  - Input: M8.E1b chain, `tools/sh4dis.py`, `tools/cecompress.py`/LZXD refs (attribution/licence checked), `decomp_oracle.py`, EXP-49 block structure (M1.2a/M1.2d).
  - Done when: `sh4dis.py` decodes the blocking shift/bit instructions in DECOMP_BLK/SECT (listed before/after in EXP) with selftests; vector file has >=3 sub-fragment cases each runtime-verified by M8.E1c/M9.29 or marked `HYPOTHESIS` with disassembly evidence and falsifier; M1.2f can cite vectors.
  - Stop: if a CE-specific LZXD variant cannot be split without a running oracle, name the minimal reproducible fragment needing QEMU/Ghidra and keep pure-Python porting blocked on M8.E1c/M9.29.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3220–C-3229

- [ ] **M9.31 — `l3check --card` baseline/no-diff verdicts for S0/S1 (unblocks M9.12)**
  - Status: open · Owner: — · Critical: no
  - Pair: solo
  - Depends: M9.41 (the US S1 evidence row this baseline needs), M9.11/M9.11b (cmp_ind_reader path), M9.6 context. **Was `M9.12 (blocked)`** — that made a deadlock: M9.31 unblocks M9.12 and M9.12's `Unblock:` is M9.31, so as written neither could ever be taken (SE 2026-11-17).
  - Goal: make the card gate produce runnable verdicts when S0/S1 are byte-identical to factory, instead of `NO_DIFFS`/exit 3 with no pass evidence. A no-diff card is a valid baseline and should still exercise registered runnable targets on factory/baseline files where safe.
  - Precheck: `python3 tools/l3check.py --selftest` passes; M9.12 EXP states the S0/S1 no-diff blocker and S2 PASS path.
  - Scope: add `--baseline` (or equivalent, name in PR) / no-diff handling to `tools/l3check.py`: when card==factory or selected diff set is empty, run registered runnable targets on the baseline/factory files they declare (or a documented minimal set) and report PASS/FAIL/SKIP/BLOCKED/not-yet-available; `NO_DIFFS` remains a distinct informational state only if no runnable target applies. Keep synthetic/vendor policy explicit. No silent PASS.
  - Input: `tools/l3check.py`, M9.12 EXP (`EXP-2026-11-08-M9.12-l3check-card`), `targets.json` target applicability metadata, `chunk_decoder_l3.py`/M9.11 path.
  - Done when: on a synthetic or documented fixture where card and factory inputs are identical, `l3check.py --card ... --factory ...` (with the chosen no-diff mode) runs at least the runnable M9.11/M9.6-equivalent paths available in that fixture and reports explicit verdicts (not bare `NO_DIFFS`/exit 3 without verdicts), with selftest/EXP evidence; M9.12 can cite it as the S0/S1 unblock path.
  - Stop: if no registered runnable target can declare a safe baseline corpus, report `NO_RUNNABLE_BASELINE_TARGETS` with reasons and keep M9.12 blocked (do not fabricate verdicts).
  - Claims: C-3320–C-3329

- [ ] **M9.41 — M9.10's last US-build gap: `point_walk_l3` runs the US reader but the target is not registered as an S1/S2 evidence row**
  - Status: open · Owner: — · Critical: yes · Pair: required
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

- [x] **M9.42 — `point_walk_l3 walk` dies with a traceback and no `result:` line on a wrong build, so M9.41's wrong-build falsifier cannot be evaluated**
  - Status: done · Owner: task/m9.42-wrong-build-verdict · Critical: no · Pair: required
  - Depends: M9.39 (done — the mutant page this falsifier names)
  - Goal: SE 2026-11-17 reproduced the gap M9.41's Falsifier depends on and found it **unsatisfiable as written**: (a) the M9.39 mutant page is a *positive* witness (it must print `result: PASS` and move `n=501` +4), not a negative control, so "the M9.39 mutant also passes" is not a failure; (b) a genuinely wrong *build* (US target on `head256.img`, or EU target on `us256.img`) raises `engine.UnmappedAccess` and exits 1 **with no `result:` line at all** (`grep -c 'result:' ` prints 0), so a script cannot distinguish "wrong build rejected" from "the tool crashed". Make the wrong-build path a clean, machine-readable verdict and fix the falsifier.
  - Precheck: `python3 tools/point_walk_l3.py walk archive/head256.img --cmp /tmp/opencode/m939/mutant-us.POINT010.DAT.cmp --ind /tmp/opencode/m939/mutant-us.POINT010.DAT.ind --page 0x840ba0 --page-len 42848 --build us2011 > /tmp/wb.out 2>&1; echo $?` prints `1` and `grep -c 'result:' /tmp/wb.out` prints `0` (the defect: crash, not verdict); the same tool on `archive/us256.img` prints `result: PASS` (the run must not change).
  - Scope: `tools/point_walk_l3.py` only: wrap the `eng.call`/`run_nth`/`run_skip` path so an `UnmappedAccess`/`IllegalInstruction` from `engine.py` becomes `result: FAIL (unmapped 0x… @ build <b>)` and exit 1 (as a build/target mismatch, not a crash); a selftest case that maps a build against an image whose text VA is unmapped; and the one-line edit of M9.41's `Falsifier:` so it names a check that can fail (a wrong-*build* run must print `result: FAIL`, and the mutant page must be labelled the positive witness it is). No verdict change for a matching build; no new VA.
  - Input: `tools/point_walk_l3.py` (`cmd_walk`, `run_nth`, `run_skip`), `tools/l3_harness/engine.py` (`UnmappedAccess`), EXP-2026-11-17-M9.39-point010-mutant (the positive witness), M9.41 block.
  - Hints: `chunk_decoder_l3.py` already turns an unmapped access into a named `Blocked`/`FAIL` line — copy that shape rather than inventing one. Keep `result: PASS` the only pass token; a crash is currently indistinguishable from a non-pass, which is the bug. The M9.39 table proves both builds read both *pages*; only the build-vs-image pairing is fatal, so the control must be a build/image mismatch, never a page mismatch.
  - Done when: the Precheck's wrong-build command exits 1 and prints exactly one `result: FAIL (unmapped …)` line (no traceback); a matching build still prints `result: PASS`; `--selftest` covers the unmapped build; M9.41's `Falsifier:` no longer treats the M9.39 mutant as a negative control; `python3 tools/selftest.py --only point_walk_l3` passes.
  - Stop: if the failure can only be detected after a stub boundary (an import), record the stub VA and hand the guard to M9.24 rather than faking a verdict.
  - Falsifier: the wrong-build run still exits on a bare traceback with zero `result:` lines, or a matching build loses its `result: PASS`.
  - Result: done in `docs/experiments/EXP-2026-11-18-M9.42-wrong-build.md` — the wrong-build `walk archive/head256.img … --build us2011` prints one `result: FAIL (unmapped 0x00000000 @ build us2011, UNMAPPED pc=0x0041db48)` and exits 1 (0 tracebacks), while `walk archive/us256.img … --build us2011` prints `result: PASS` and exits 0; the selftest covers `run_skip`, `guarded` and the verdict.
  - Claims: C-4430–C-4439

- [x] **M9.43 — M9.39's mutant pair is only reproducible from a pasted heredoc; the committed `mutate_refer_poi.py` CLI writes a different, all-149-stream corpus**
  - Status: done · Owner: task/m9.43-mutate-cli-chunk-preserving · Critical: no · Pair: required
  - Depends: M9.39 (done — the EXP whose corpus this must reproduce)
  - Goal: SE 2026-11-17 ran the committed CLI as the EXP's `Reproduction` implies (`mutate_refer_poi.py … --page 0x840ba0 --old … --new … --resize`) and it printed `outer .cmp 4240574 -> 4233456 bytes, 149 chunk(s)`, sha `5565c9ba…` — **not** the EXP's pinned `ea2d0e0f…` (4,240,400 B, one differing stream). The chunk-preserving path the EXP's `Method` uses (`cmpind_codec.repack_changed_chunks`) exists only inside a `python3.13 - <<'PY'` heredoc, so rule 16's "commands run as written" fails: a reader cannot regenerate the L3 corpus M9.41 cites as its control.
  - Precheck: `python3 tools/mutate_refer_poi.py /home/marek/projekty/leafre-work/m5.12-us/root-factory/REFER001/POINT010.DAT.cmp …/POINT010.DAT.ind /tmp/cli --page 0x840ba0 --old 'HAWAII ST GOVT FREQNTLY CLLD NMBRS' --new 'HAWAII ST GOVT FREQNTLY CLLD NMBRSXXXX' --resize` prints `149 chunk(s)` and its `.cmp` sha is not `ea2d0e0f…` (the defect); `grep -c "python3.13 - <<'PY'" docs/experiments/EXP-2026-11-17-M9.39-point010-mutant.md` is `2` (two heredoc-only builders).
  - Scope: `tools/mutate_refer_poi.py` only: add a chunk-preserving rebuild mode (e.g. `--chunk-preserving`, default for `--resize`) that reuses every unchanged 64 KiB outer stream via `cmpind_codec.repack_changed_chunks` and rebuilds `.ind` offsets, keeping the existing whole-blob path behind an explicit flag for the copy-scan use (M5.12c/M5.27); a `--selftest` case asserting the single-differing-chunk property; then replace the two EXP heredocs with the committed command (or re-pin the EXP to the SHAs the committed command prints). No page semantics change, no new mutation type.
  - Input: `tools/mutate_refer_poi.py` (`main`, `refit_page_budget`, `encode`), `tools/cmpind_codec.py` (`repack_changed_chunks`, `build_ind`), `tools/slot_budget.py` (`fit_page_inplace`), EXP-2026-11-17-M9.39-point010-mutant (Method step 3 + C-4173), the CLI run above.
  - Hints: the EXP needed level 9 / memLevel 9 for the changed chunk because `factory_compress` overflowed the slot (C-4175); the mode must keep that documented fallback, not silently emit a bigger stream. `cmpind_codec.repack_changed_chunks` is already the single-chunk owner — call it, do not re-implement it. The C-4173/C-4174 SHAs are the acceptance oracle for "same corpus"; if a zlib change moves them, the EXP must state the runtime (`tools/zlibinfo.py`), as C-4175 already does.
  - Done when: the committed chunk-preserving command reproduces the EXP's `.cmp`/`.ind` SHAs on the runtime the EXP names (or the EXP is corrected to the SHAs the command prints, with the runtime recorded); `grep -c "python3.13 - <<'PY'"` over the EXP's Method is `0`; `python3 tools/selftest.py --only mutate_refer_poi` passes; the M5.12c whole-blob copy-scan path still runs.
  - Stop: if the level-9 fallback cannot be made deterministic across the supported zlibs, keep the heredoc, but commit it as `tools/build_point010_mutant.py` with `--selftest` and re-point the EXP — do not leave a corpus that only a session can rebuild.
  - Falsifier: the committed CLI (with the new mode) still changes all 149 streams, or the EXP still has no committed command that prints its pinned mutant SHAs.
  - Claims: C-4480–C-4489
  - Result: `docs/experiments/EXP-2026-11-18-M9.43-mutant-cli` (C-4480–C-4489). `mutate_refer_poi.py` now defaults to the chunk-preserving outer rebuild (`cmpind_codec.repack_changed_chunks`, `--whole-blob` for the old path). On stock zlib 1.3.2 the committed command prints the M9.39 pins: US `.cmp` `ea2d0e0f…` (4,240,400 B) / `.ind` `5d576d62…`, EU `.cmp` `e75c298f…` (3,271,483 B) / `.ind` `077937ea…`, `changed chunk(s) [132]`/`[110]` (1 of 149/151 stream(s) differ); the four walks reproduce `n=501` +4; `grep -c "python3.13 - <<'PY'"` over EXP-M9.39 is `0` (Method + control replaced); `--selftest` 13/13; `l2check` on the EU factory tree PASS; `gate.py` 4 pass.

- [ ] **M1.33 — M1.22's census and relocated-body tables come from an uncommitted script, and its Method has ellipses**
  - Status: open · Owner: — · Critical: no · Pair: required
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

- [ ] **M9.32 — Reconcile M9.11: `cmp_ind_reader` meets done-when or block precisely**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M9.11, M9.11b
  - Goal: close the M9.11 reopen cleanly: M9.11b registered `cmp_ind_reader` as `firmware_call` with declared sec1 `inflate_mask[17]` provenance, but M9.11 remains open with stale precheck/scope text and its done-when requires all three POINT010 pairs + controls through the firmware path/target.
  - Precheck: `python3 tools/chunk_decoder_l3.py --selftest` and `python3 tools/l3_harness/runner.py --selftest` (or bounded equivalent) pass; `targets.json` contains `cmp_ind_reader` `firmware_call` with `sec1_table`; factory/S1/S2 POINT010 pairs available per rule 11 (M5.13b tree or fetchable inputs).
  - Scope: verify M9.11 done-when end-to-end: for factory, S1, S2 pairs page `0x840ba0` byte-identical to `cmpind.py extract` via the registered runner target (or documented equivalent that exercises the same registered path for all pairs), plus corrupt-`.ind` and swapped `+4`/`8` controls as in EXP-2026-11-08-M9.11-chunk-decoder. Update M9.11 task text (precheck/scope/note) to reflect M9.11b. No new format claims.
  - Input: `tools/l3_harness/runner.py`, `targets.json`, `tools/chunk_decoder_l3.py`, `tools/cmpind.py`, EXP-2026-11-08-M9.11-chunk-decoder, EXP-2026-11-08-M9.11b-firmware-call-target, M5.13b S1/S2/factory pairs.
  - Done when: M9.11 is `done` with `Result:` naming an EXP that records all three pairs + controls passing through the registered target/path and cites sec1-table provenance, OR M9.11 is `blocked` with the exact missing pair/control/runner gap and `Unblock:` named. No stale "no firmware-call entry kind" text remains in M9.11.
  - Stop: if S1/S2 corpora are unavailable and cannot be obtained by existing tools, block with missing corpus named (do not claim all-pairs pass on factory only).
  - Claims: C-3370–C-3379

- [ ] **M9.33 — Map reopened L3 target rerun prerequisites (M1.2f / M9.24 / M9.28 / H45)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: H45, M9.28
  - Goal: make "re-run reopened L3 reader targets" cheap to decide: for M9.6/M9.10/M9.13/M9.14/M9.17/M9.11 (open states), state which blockers are cleared (M9.20/M9.11b/M3.20) and which prerequisites remain (sec1 decompression M1.2f, import/CRT/file binding M9.24, input-buffer mapping M9.28, reader VA/signature evidence), using H45 verdicts where available.
  - Precheck: `test -f tools/l3_precond.py` or the H45-delivered tool exists and `--selftest` passes (else task becomes `blocked` on H45 with that named).
  - Scope: docs/planning output (EXP or a small table update in `docs/research/reader-coverage.md` notes / TODO task notes, named in PR) — no firmware execution, no silent PASS. Keep rule 13: verdict tables are planning aids, not L3 results.
  - Input: H45, M9.28, targets.json, reader-coverage matrix, EXPs for M9.6/M9.11/M9.13/M9.14/M9.17, M1.2f/M9.24 task texts.
  - Done when: each reopened/blocked L3 reader target above has an explicit `READY|BLOCKED|UNKNOWN` prerequisite verdict with missing dependency IDs (or "H45 unavailable") recorded in an EXP; TODO/coverage notes reference it. No target is marked runnable without evidence.
  - Stop: if H45 is unavailable and target metadata is insufficient, record `UNKNOWN` with missing fields and stop (do not guess).
  - Claims: C-3400–C-3409

- [ ] **M9.34 — Close M9.32 as satisfied by M9.11 closeout (board/EXP linkage)**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M9.32, M9.11, M9.11b
  - Goal: remove stale L3-board state now that M9.11 closeout has satisfied M9.32's done-when; keep evidence explicit without duplicating claims or re-running vendor-image checks unnecessarily.
  - Precheck: `test -f docs/experiments/EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md`; confirm M9.11 is `done` with Result naming that EXP and M9.32 is still `open`; `python3 tools/claims_check.py` and `python3 tools/todo_check.py` pass.
  - Scope: TODO status/text reconciliation for M9.32 (and only stale precheck/scope wording in M9.11 if still misleading, keep edits minimal/local). No new firmware execution, no format claims, no vendor bytes.
  - Input: EXP-2026-11-09-M9.11-closeout-cmp-ind-reader.md, EXP-2026-11-08-M9.11-chunk-decoder.md, EXP-2026-11-08-M9.11b-firmware-call-target.md, TODO M9.11/M9.32 blocks.
  - Done when: M9.32 is `done` or `blocked` with `Result:` that cites the M9.11 closeout EXP as satisfying all three pairs + controls through the registered `cmp_ind_reader` path with declared sec1 provenance; M9.11/M9.32 contain no stale "not registered"/"no firmware-call entry kind" blocker text except accurate history; `todo_check.py` and `claims_check.py` pass.
  - Stop: if the closeout EXP does not actually cover a M9.32 done-when element (pair/control/runner path/corpus availability claim), record the exact gap and keep M9.32 `blocked` naming it — do not close on incomplete evidence.
  - Claims: C-3430–C-3439

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

- [ ] **M9.36 — Re-run every L3 probe and blocker on the corrected PySh4**
  - Status: open · Owner: — · Critical: yes
  - Depends: — (H51 engine fix is on `main` with this task)
  - Goal: until H51, `mov.b R0,@(disp,Rn)` and `mov.w R0,@(disp,Rn)` stored through `r0` instead of `Rn` — silently. Any earlier run that executed one of them wrote to a wrong address: an `UNMAPPED 0xffffffxx` stop is the visible form, a store into a mapped region is the invisible one. Find out which recorded L3 results change.
  - Precheck: `python3 tools/l3_harness/engine.py --selftest` shows the check "mov.b/mov.w R0,@(disp,Rn) base is Rn; mul.l any Rm; movca.l (H51)".
  - Scope: every target in `tools/l3_harness/targets.json`, `point_walk_l3.py` (`walk`, `skip`), `chunk_decoder_l3.py` (factory, S1, S2, `corrupt-ind`, `swap-4-8`), the M9.35 probes (`mmain_reader`, `drstr-sub_00419350`), M9.6, M9.13, M9.20 and the sub-accessor runs of M3.11c. Before/after on the same inputs.
  - Input: the EXPs of those tasks give the commands; `git stash`/a worktree at `116c826` gives the old engine for the "before" column where the EXP has no number.
  - Hints: `drstr-sub_00419350` stopped at `UNMAPPED 0xfffffec6..0xfffffec8` (M9.35) — a 2-byte store just below zero is exactly what `mov.w r0,@(disp,Rn)` with a small negative `r0` produced; expect that stop to move. To see whether a run is affected without re-running it, count the opcodes `0x80xx`/`0x81xx` in the functions it executes (`sh4dis` + pdata length).
  - Done when: an EXP table `target / input / before / after / changed?`; every changed verdict is corrected in its task block, `reader-coverage.md` and `claims.md`; M9.14 and M9.17 carry the new next stop.
  - Stop: a target that needs corpus files not obtainable in the session is listed `NOT RE-RUN` with the reason.
  - Claims: C-3580–C-3589

- [ ] **M9.37 — Decoder audit: every instruction form PySh4 models, tested with distinct registers and compared with `sh4dis.py`**
  - Status: open · Owner: — · Critical: yes
  - Depends: —
  - Goal: three decode defects survived five days of L3 work because the engine's own tests used operand values that hide a register mix-up (`n == 0`, `m == 0`). Make that class of defect impossible to miss, and know which opcodes of the firmware the engine cannot run at all.
  - Precheck: `python3 tools/l3_harness/engine.py --selftest`; `python3 tools/sh4dis.py --selftest`.
  - Scope: (1) a table-driven selftest: for each modelled form one case where `Rn`, `Rm` and `R0` are three different registers holding three different values, and the expected effect is written from the SH-4 manual encoding (`nnnn` = bits 11–8, `mmmm` = bits 7–4, the 0x8xxx forms have `Rn`/`Rm` in bits 7–4); (2) a differential check: for every distinct opcode in the pdata-covered code of `Navi.exe` and `nk.exe`, the engine's decode class and operand registers equal those of `tools/sh4dis.py` (two independent tables); (3) a census: opcodes present in the firmware that the engine raises `IllegalInstruction` for, with counts. Floating point may stay unmodelled, but counted.
  - Input: `tools/l3_harness/engine.py` (`_exec_*` dispatch), `tools/sh4dis.py`, `binutils-sh4-linux-gnu` `objdump -b binary -m sh4 -EL` as a third opinion where the two tables disagree.
  - Hints: the H51 defects were in `_exec_branch8` (0x80/0x81) and `_exec_misc` (`pattern = insn & 0xF0FF` matched `mul.l` only when `Rm = r0`). Look at every `pattern ==` comparison in `_exec_misc`/`_exec_system` for the same mistake, and at `mac.l`/`mac.w`, `div1`, `rotcl/rotcr`, `addc/subc/negc` T-flag handling — the decompressor and zlib exercise only part of them.
  - Done when: the selftest has one distinct-register case per modelled form; the differential check reports 0 disagreements or each one is fixed/explained; the census is in the EXP; the M9.36 targets still pass.
  - Stop: an opcode family that needs FPU or MMU state is listed as out of scope.
  - Claims: C-3590–C-3599

- [x] **M9.39 — A POINT010 page whose *records* differ: the L3 corpus M1.22 left to M9.10**
  - Status: done · Owner: task/m9.39-point010-mutant · Critical: no · Pair: required
  - Result: EXP-2026-11-17-M9.39-point010-mutant; C-4170–C-4178 — a +4 B rewrite of record 500 moves `n=501`/998/999 by +4 on both builds and both pages (US `0xfe4e→0xfe52`, `0x1fb82→0x1fb86`, `0x1fc0a→0x1fc0e`; EU `0xbe82→0xbe86`, `0x17af6→0x17afa`, `0x17b40→0x17b44`), count stays 1,000, `n=1000` is `None`, one outer stream of 149/151 differs; a same-length control leaves every offset at the factory value.
  - Depends: M1.22 (both walkers run on US + EU pages; done), `tools/mutate_refer_poi.py` (for the record edit)
  - Goal: M1.22's cross-build run uses two *different factory cards*, which proves the reader is not tuned to one card but not that it reads *our* bytes. The L3 corpus still has no POINT page whose record contents (name offset, coordinates, icon) were changed on purpose, so a reader that ignored the record bytes would still pass. Produce one mutated page and run all four combinations (EU/US code × factory/mutated page) so the mutation is visible in the output, not just "PASS".
  - Precheck: `python3 tools/mutate_refer_poi.py --selftest` passes; `python3 tools/point_walk_l3.py walk archive/us256.img --cmp <US>/POINT010.DAT.cmp --ind <US>/POINT010.DAT.ind --page 0x840ba0 --page-len 42848 --build us2011 | tail -1` prints `result: PASS` (the M1.22 baseline this task must not regress).
  - Scope: one mutated `POINT010` pair written outside the repo (`archive/` only; commit hashes, offsets and the record diff, never bytes), the four L3 runs, and the OP-level observation that a moved name/coordinate changes the firmware's returned offset but not the record count. No map-format claim and no writer change.
  - Input: `tools/mutate_refer_poi.py` (record name/offset edit), `tools/point_walk_l3.py` (`walk`, `skip`, `--build`), `tools/cmpind.py`/`cmpind_writer.py` to rebuild the pair, `archive/us256.img` + `archive/head256.img`, a `POINT010` pair from either factory tree.
  - Hints: mutate a record the walker already samples (`n=500` or `n=998`) so the change lands in the printed table; run the unmutated page first as the positive control and the mutated page second; a reader that returns the factory offset for the mutated record is the failure this task exists to expose. Rebuild only the 64 KiB chunk that holds the record (AGENTS "Writing data back"), keep the other streams verbatim, and record the `.ind` offset change.
  - Done when: an EXP table `code build / page / sampled records / result` shows the mutated record's firmware offset differs from the factory one in all four runs (or a named, justified case where it does not), the record count is unchanged, and the mutated pair's `.cmp`/`.ind` SHA-256 and the record's byte offset are in the record; `python3 tools/gate.py` green.
  - Stop: if the mutation changes the record count or the walker stops before the sampled record, treat it as a corrupt page, record the stop, and pick a record whose length does not change rather than resizing the page.
  - Falsifier: every run prints the same offsets for the mutant and the factory page (the reader ignored the record bytes).
  - Claims: C-4170–C-4179

- [ ] **M9.40 — `chunk_decoder_l3 --build` names the US `inflate_mask` in C-3535, but the run maps a constant**
  - Status: open · Owner: — · Critical: no · Pair: required
  - Depends: — (M1.22's `--build` selector and US table are on `main`)
  - Goal: M9.11b found the EU `inflate_mask[17]` by deriving it from `inflate`'s own `shll2` load, and M1.22 added a US `BUILD_TARGETS["us2011"]["inflate_mask"] = 0x005987B0`; C-3535 then says the US run uses "the US `inflate_mask` from the unique `shll2; …` site". That US value is used, but the [17] table is **written**, not read: `chunk_decoder_l3.run()` puts the public zlib `2^n - 1` series at the build's VA, so no firmware byte and no harness assertion proves the US and EU VAs actually hold that table. The verdict (byte-identical decode) is sound; the provenance sentence in C-3535 overstates what was verified.
  - Precheck: `sed -n 242,252p tools/chunk_decoder_l3.py` shows `inflate_mask` written from `(1 << n) - 1`, not read from the image; `python3 tools/chunk_decoder_l3.py --selftest` passes; `python3 tools/chunk_decoder_l3.py run archive/us256.img … --build us2011` prints `verdict: PASS` (the run this provenance must not change).
  - Scope: `tools/chunk_decoder_l3.py` (a `--read-mask` path that loads the table from the image at the build's VA and fails if it differs from `2^n - 1`, or an explicit `OBSERVED not read` in the log), the C-3535 wording, and the M1.22 EXP's mask sentence. No verdict change, no new firmware search, no EU target change.
  - Input: `tools/chunk_decoder_l3.py` (`BUILD_TARGETS`, the `zero-mask` branch at ~line 242), `tools/cerom.py` (`va2file`) or `tools/va_class.py` to map the VA, C-3535, EXP-2026-11-17-M1.22-us-build-census.
  - Hints: the two VAs may both be `INIT`/BSS (H49: 94 % of compressed sec1 is zero) — if so, the honest result is "the value cannot be read; the mask is the public zlib constant written at the build's own slot", and C-3535 loses the "from the US site" clause. Do not turn a write into a read to make the claim true.
  - Done when: the log line says whether the mask was **read** from the image or **written** from public zlib, per build; a negative control (a deliberately wrong series at the US VA) either fails the read or is reported as `OBSERVED (not read)`; C-3535 and the EXP say only what the run did; `--selftest` and `python3 tools/gate.py` green; the EU/US decode verdicts are unchanged.
  - Stop: if `va_class.py` says both mask VAs are `INIT`, record `OBSERVED: mask is written (public zlib), VA is INIT` and stop — M1.19 is the task that makes them readable, not this one. If C-3535's edit would re-open an M1.22 claim, keep M1.22's wording as printed at `3d79bcc` and mark the correction `Superseded by` this task's EXP instead of editing a done row.
  - Falsifier: C-3535 still claims the US mask was taken from the image after the change, or the change alters either build's decode verdict.
  - Claims: C-4180–C-4189

- [ ] **M9.38 — Read-watch tracer: which functions read the page buffer**
  - Status: open · Owner: — · Critical: yes
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

- [ ] **M9.44 — Virtual card: stub the three stdio wrappers once and let the firmware's file layer read a card tree ("software S0")**
  - Status: open · Owner: — · Critical: yes · Pair: required
  - Depends: M9.36 (trust the engine first), M1.19 helps (`INIT` bytes); M3.26 gives names but is not required
  - Goal: the nearest thing to putting a card in the unit that needs no unit. Today each L3 target stubs imports one by one (M9.24) and maps its input by hand (M9.28). The firmware reads map files through three wrappers — `fopen` `0x0041b3bc`, `fseek`/`ftell` `0x0041b470`, `fread` `0x0041b4f8` (EU2011, H101). Replace those three with host stubs that serve files from an extracted card tree, and the real `DRSTR`, `MMAIN`, `CMP.LST` and `.cmp` code runs on whole files, factory or generated.
  - Precheck: `python3 tools/callgraph.py users g.json fread,fseek,fopen` shows the three wrappers; `python3 tools/sh4dis.py IMG256 Navi.exe --image-start 0x200200 --va 0x0041b4f8 --count 40` shows one `fread` import call (arguments `r4…r7` are passed through or re-ordered — record which).
  - Scope: `tools/l3_harness/`: a `vcard` stub set (`--card-root DIR`): path translation from the firmware's `\SystemSD\…` strings to the tree, a handle table, `fopen`/`fseek`/`ftell`/`fread`/`fclose` semantics, a log of every `(file, offset, length)` read. Targets, in this order: `mmain_reader` (`0x0041a438`), `drstr_parser` (`0x00419684` → `0x00419350`), the `CMP.LST` opener `0x0041ba90`, then the mount state machine `0x00419ca0`. EU2011 code on the EU tree first; US2011 addresses from `fn_match` after.
  - Input: `tools/l3_harness/runner.py`, `stubs.py`, `rommap.py --bss-zero` (M9.35), `tools/callgraph.py`, the M9.14/M9.17 reopen EXPs (current stops: `wcstombs` stub for `mmain_reader`; an unmapped store for `drstr`, suspect after H51), `python3 tools/verify.py --image IMG` for the tree.
  - Hints: stubbing the *wrapper* (a function of ours-to-define contract: read its 40 instructions once) is safer than stubbing `coredll!fread` behind it, because the wrapper also does the firmware's error handling (`ferror`/`clearerr`) that we do not want to model. The read log is a result in itself: the list of `(offset, length)` the firmware reads from `DRSTR001.DAT` is the reader's view of the format, and comparing it between the factory file and our rebuilt file is a rule-13 test with no interpretation. Negative controls come free: truncate the file, flip the `0x2f` byte, remove `CMP.LST`.
  - Done when: `runner.py run mmain_reader --card-root ROOT` and `run drstr_parser --card-root ROOT` return a verdict on the factory EU tree and on the M5.6 rebuilt tree, with identical read logs or a listed difference; three negative controls each change the verdict or the log; `reader-coverage.md` rows 3–5 updated; M9.24 and M9.28 closed as covered or narrowed.
  - Stop: a stop at an `OSM_TaskSend`/message import means the function waits for another task — record the message and make that the next target; do not fake the reply.
  - Falsifier: the factory tree gives a reject verdict (then the harness, not the card, is wrong).
  - Claims: none yet

- [ ] **M9.45 — PySh4 ten times faster, measured on the decompressor**
  - Status: open · Owner: — · Critical: no · Pair: solo
  - Depends: M9.37 (the decoder audit is the regression suite for this change)
  - Goal: PySh4 runs about 260,000 instructions per second (H51: 183,114 instructions in 0.7 s). `nk_decomp.py check` takes ten minutes, and anything longer than one reader function is out of reach. Whole-task emulation (M9.44's mount machine, later a headless `Navi.exe` map task) needs an order of magnitude.
  - Precheck: `time python3 tools/nk_decomp.py section IMG256 --module Navi.exe --index 1` (about 16 s; the output SHA-256 is in EXP-2026-11-11-H51).
  - Scope: `tools/l3_harness/engine.py` only. A predecode cache (opcode at VA → bound handler with operands extracted once, invalidated on a write to an executable region), register file as a list instead of a dict of names, memory regions found by bisect with a last-hit cache. No change of behaviour; no C extension (stdlib rule).
  - Input: `python3 -m cProfile -s cumtime tools/nk_decomp.py section …` first — optimise what the profile shows, not the list above.
  - Done when: the benchmark is ≥ 8× faster with the same output SHA-256; `engine.py --selftest`, `selftest.py` and the M9.36 table are unchanged; the EXP has the profile before and after.
  - Stop: at 3× with the profile flat, record it and stop.
  - Claims: none yet

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
