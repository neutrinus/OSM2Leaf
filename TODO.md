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
    *accepted* only when an L3 target runs that reader on our generated file
    and gets the expected values (an M9 task). Round-trip tools and L2 are
    necessary, not sufficient. The live status of each file type is the
    matrix in [`docs/research/reader-coverage.md`](docs/research/reader-coverage.md)
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

## Priorities (product review 2026-11-08, tenth pass)

Earlier passes are frozen in
[`docs/research/todo-history-2026-11-06.md`](docs/research/todo-history-2026-11-06.md).
The ninth pass (same day) stands; this pass audits the 15 results merged after
it (`476dfb0..95a4b42`, 23 commits) and re-sequences the board.

**Nearest milestone: the two test cards exist; the bench is next.** M5.13b
built S1 and S2 on the real US image (S1 byte-identical to factory, S2 differs
only in `POINT010` plus its directory entry; `cardcheck.py --image` passes).
Caveats remain: the diff-range cluster base was derived from the `imgpatch`
write offset (not an independent BPB read), and the rebuild used stock zlib
1.3.2. M1.13 shows stock zlib L6/mem8 is release-indistinguishable from the
factory encoder (471/471 `POINT001–009` pages), so 1.3.2 is fine; the BPB
check is still worth hardening. **M6.2 → M6.5 → M6.6** waits on Marek.

**Encoder premise corrected (M1.13).** The ninth pass said "stock zlib 1.3.x is
0.8 % larger than the factory encoder" and filed M1.13 to find the encoder.
M1.13 reproduced **471/471** factory inner pages with stock zlib L6/memLevel 8
(1.1.3–1.3.2 indistinguishable); zlib-ng 0/471; `tools/factory_zlib.py` added.
The 0.8 % premise is not reproduced (C-2575). M5.12c's 5 unfit *edited* pages
are therefore a **slot-budget** problem (edited content compresses worse than
the original slot allows), not a missing encoder — **M5.21** is the fix,
without an encoder dependency.

**L3 readers re-opened, then blocked on compressed `.data` (not on the
harness).** M9.20 (`562215a`) closed the harness plumbing and M9.6 (`ff8720d`)
the map-code comparator. M9.14/M9.17 were re-opened (rule 15) and ran: they now
hit **compressed `Navi.exe` sec1** (`.data`, `0xc8002040` — consistent with
C-2128: executables are readable, data is not). M9.14 needs M1.2f + **M9.24**
(import binding and coredll file stubs); M9.17 needs M1.2f. M9.11's firmware
chunk decoder passes byte-identically on the factory/S1/S2 pairs (and rejects
corrupt/swapped controls), but `cmp_ind_reader` cannot be registered until
**M9.11b** (a firmware-call target kind). M9.22 explained `B30R048R` (three
records with a layer table past `geo_len`) and re-set the L2 pin; **M9.23**
models them.

**Reader searches: new negatives, correctly scoped.** M3.14 found no
`ZCODE0nn`/`COORD001` reader body in decodable build-A code (ICODE001 only the
opener `0x003f2cc0`); M3.15 reached the LCTBL walker only through compressed
sec1 helpers — both blocked on M1.2f (for the `.data`/helper path). M3.11b
found the POINT page already in native little-endian `u16` in the decoded
buffer (C-2234) but left the source unknown (HYPOTHESIS, C-2239). M4.16b
verified the C-884 directory-walk functions but could not run the walk:
`sh4dis.py` lacks MOVT/SHAR/SHLD/SHAD — **M1.11c**. M4.22 matched code
counts but could not name the `0x18c` language codes (OQ-44).

**Compiler spine moved.** M5.4 splices real OSM roads into EU 2011 factory
`B48R048R` and L2 passes (structural; DRSTR rebuilt, no golden), limited to
one `0x2046` directory, 18 parcels, level 1, provisional classes and a stale
router graph (M5.6). Non-`0x2046` directory kinds are a follow-up (**M5.22**).
M4.17 mapped 96 numbered LCTBL roads (420 rows, EU 2011/2014) with controls but
established **no** road-class field (LORO fails); `class_code` is a hypothesis
(C-1825) and does not give M4.2 an RDSTM row key. M5.12c is **blocked**: the
uncompressed-files exact scan never finished (done-when not met).

**What the tenth pass verified (methodology):**
- M4.17, M9.11, M9.14/17, M3.14/15, M4.16b, M4.22 and M5.12c all set `blocked`
  (or reported a negative) when the done-when was not met — no false `done`.
- M1.13 named its candidate with a version and used a negative control; it
  corrected the board's premise instead of fitting it. M5.21's text now
  reflects that result.
- M9.14/M9.17 re-blocked on a *different* cause (compressed sec1 `.data`) than
  their original harness block — rule 15 was followed, and the new blocker is
  recorded with a new EXP.
- M5.4's L2 pass is explicitly structural (no golden, DRSTR rebuilt); the
  geometry read-back is the content check. Honest scope.

**Take these first (critical, ready, unowned), in this order:**

1. **M1.11c** (MOVT/SHAR/SHLD/SHAD) → unblocks the M4.16b directory walk; and
   **M9.11b** (firmware-call target kind) → registers `cmp_ind_reader`.
2. **M5.21** (slot budget, refuses/repacks, never overruns) — M1.13 removed the
   encoder excuse; edited pages that outgrow their slot are the real limit.
3. **M1.2f** (DECOMP_BLK) — still the gate for `.data`/sec1: it unblocks
   M9.14/M9.17 (with M9.24), M3.14/M3.15, M3.2/M3.2b and M1.3/M1.4.
4. **M9.24** (import binding + coredll file stubs), after M1.2f — needed for
   M9.14/M9.16.
5. **M3.11c** → **M9.10**; **M3.2b/M3.13** re-runs with the corrected method;
   **M4.23** → M4.3.
6. **M5.6 → M5.11** on the compiler spine (M5.4 done; M5.3/M5.22/M5.23 still
   constrain it); **M2.4** runs on M9.6's comparator.

**Needs Marek:** S1/S2 on the unit (M6.2 S0 → M6.5 S1 → M6.6 S2), the Pico
`.uf2` built locally (M6.11), and non-Claude tasks (M9.2 Ghidra; M1.2e).

**Phase-2 milestone (unchanged):** one OSM-generated Dolnośląskie tile on a
card image that passes L1 + L2 + `realcheck.py` and every known gate (M5.11),
gated by M5.3 (road classes), M5.22 (directory kinds), M5.6 (indices) and the
firmware/L3 confirmation chain (rule 13).

## Workstreams at a glance

| Stream | Front | Ready now (no open deps) |
| --- | --- | --- |
| H | Housekeeping | **H19, H21**; H13–H18/H20 done |
| M1 | Firmware tooling | **M1.11c, M1.12, M1.14**; M1.2f for `.data`/M1.3/M1.4; M1.2e non-Claude; M1.13 done |
| M2 | Map code, activation, updater | **M2.4, M2.14, M2.17**; M2.15/M2.16 done |
| M3 | Reader contract | **M3.11b, M3.11c, M3.13, M3.16, M3.18, M3.20**; blocked on M1.2f: M3.2, M3.2b, M3.14, M3.15; M3.17 done; M3.19 blocked (→M3.20) |
| M4 | Data formats | **M4.16c, M4.16d, M4.24, M4.25, M4.26, M4.27, M4.29**; blocked: M4.2 (no RDSTM row key), M4.3/M4.23 (→M4.24–M4.26), M4.8b (→M4.8d), M4.16b (→M1.11c), M4.22 (OQ-44), M4.28 (→M4.27); M4.21 after M3.6 |
| M5 | Compiler + US edits | **M5.3, M5.5, M5.6, M5.11, M5.14, M5.15, M5.20, M5.21, M5.22, M5.23**; blocked: M5.12c (scan unfinished); M5.4/M5.13b done; M5.16–M5.19 after their M3 readers |
| M6 | Hardware (Marek) | **M6.2 (S0)**; M6.5/M6.6 after M5.13b (done); M6.7 after M5.14 |
| M8 | Full-system emulation | **M8.A2, M8.E1**; M8.A3 after M8.A2 |
| M9 | L3 toolkit | **M9.10** (after M3.11c), **M9.11b, M9.12, M9.15, M9.23, M9.24** (after M1.2f); blocked on M1.2f: M9.13, M9.14, M9.17; M9.6/M9.11/M9.20/M9.21/M9.22 done; M9.2 non-Claude |

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

- [ ] **H25 — Fundament CI (GitHub Actions): bramka PR bez danych vendorowych**
  - Status: open · Owner: — · Critical: yes
  - Depends: H24 (żeby `selftest.py` nie dawał fałszywego FAIL przez `mkcard`/tmp; H23 zalecane dla higieny TODO)
  - Goal: każdy PR i push do `main` dostaje deterministyczną bramkę jakości sygnału testowego (nie coverage): repo się parsuje, narzędzia mają spójne selftesty, ledger/board są niesprzeczne. To mierzy „czy infrastruktura testów działa”, nie „czy auto czyta kartę”.
  - Precheck: `ls .github/workflows` zwraca brak workflowów (stan bieżący); `python3 tools/selftest.py --list` działa lokalnie. Jeśli istnieje już workflow o tej samej roli, zadanie redukuje się do uzgodnienia z nim (nie duplikować).
  - Scope: nowe pliki `.github/workflows/*.yml` (nazwy ustalone w EXP/PR), uruchamiane na `pull_request` i `push` do `main`. Joba/joby: checkout, Python 3.11 + 3.13 (macierz minimalna; opcjonalnie 3.14 osobno jako informacyjna, bo zlib-ng — patrz H9), `python3 tools/selftest.py` (z jasną polityką SKIP: brak `--selftest`/brak zależności = SKIP, nie PASS), `python3 tools/claims_check.py`, oraz lint TODO gdy H24 dostarczy narzędzie. **Poza zakresem:** pobieranie obrazów vendorowych, testy wymagające `IMG256`/pełnego drzewa, budowa QEMU, L4. Workflow nie może zawierać sekretów ani danych vendorowych.
  - Input: `tools/selftest.py`, `tools/claims_check.py`, `tools/README.md` (konwencje), reguły H9 (zlib-ng nie udaje byte-identical; job kompresji/rebuild oznaczyć lub uruchamiać pod stock zlib). Artefakty: logi, opcjonalnie `selftest --json`.
  - Done when: workflow jest poprawny składniowo, uruchamia się w CI, publikuje czytelne podsumowanie (ile PASS/FAIL/SKIP i które narzędzia zawiodły), a FAIL blokuje merge check; dokumentacja w `tools/README.md` lub `.github/workflows/README.md` opisuje co jest bramką twardą, co informacyjną i dlaczego brak vendor data. EXP z linkiem do przebiegu CI i uzasadnieniem macierzy Pythona.
  - Stop: jeśli `selftest.py` ma niestabilne SKIP/FAIL zależne od środowiska GHA (brak `qemu-system-sh4`, `binutils-sh4`, miejsca na dysku), sklasyfikować je jawnie (SKIP z powodem) zamiast maskować; problematyczne przypadki → osobne taski, status zadania `blocked` z `Unblock:` tylko gdy bramka nie może być zielona z uczciwą klasyfikacją.
  - Claims: C-2750–C-2759

- [ ] **H26 — Pipeline L1/L2 na fixture’ach syntetycznych i generowanych (CI)**
  - Status: open · Owner: — · Critical: yes
  - Depends: H25
  - Goal: automatycznie mierzyć postęp warstwy „format/struktura akceptowalna offline”: potrafimy zbudować lub zmutować dane tak, że `cardcheck.py` (L1) i wybrane ścieżki `l2check.py`/round-trip przechodzą — bez twierdzenia, że firmware je zaakceptuje. To bezpośredni wskaźnik celu „generować obrazy kart SD”, ograniczony do tego, co da się udowodnić offline.
  - Precheck: `python3 tools/cardcheck.py --selftest`/help i `python3 tools/l2check.py --selftest`/help działają; istnieją narzędzia generujące fixture (`mkcard.py`, `imgpatch.py`, `cmpind_writer.py`, `drstr_ze0`/harness tam gdzie mają `--selftest`). Jeśli brak syntetycznego wejścia dla danej ścieżki L2, ścieżka jest raportowana jako `NOT COVERED`, nie jako PASS.
  - Scope: job/workflow (może rozszerzać H25, osobny plik lub wspólny) uruchamiający: (a) L1 na obrazie/drzewie wygenerowanym w teście z fixture syntetycznego (np. ścieżka `mkcard`/minimal tree — zgodnie z aktualnymi narzędziami; nie commitować vendor danych), (b) round-tripy L2 oparte o selftesty/narzędzia: `cmpind` preserved/recompress tam gdzie stock zlib dostępny, DRSTR rebuild, tile round-trip na syntetycznych/małych przypadkach obsługiwanych przez narzędzia, mutacja POI tam gdzie fixture jest syntetyczny. (c) Jawny raport: `L1 synthetic`, `L2 DRSTR`, `L2 cmp/ind`, `L2 tile`, `L2 POI mutation` — każdy PASS/FAIL/SKIP/NOT COVERED z komendą. **Poza zakresem:** golden EU2011 na prawdziwym `ROOT` (wymaga vendor tree), pełne 194 pary na prawdziwym REFER001, `--include-lev` na prawdziwym pliku.
  - Input: `tools/cardcheck.py`, `tools/l2check.py`, `tools/cmpind.py`, `tools/mkcard.py`, `tools/imgpatch.py`, `tools/selftest.py`; golden/profile tylko jeśli są w repo i nie zawierają danych vendorowych (`tools/golden/eu2011.json` to hashe/liczniki — użyć ostrożnie, bez wymagania obrazu).
  - Done when: CI produkuje artefakt JSON/Markdown z macierzą L1/L2 (per check) i exit code odzwierciedla tylko checks uznane za „runnable” w tej warstwie; dodanie nowego syntetycznego przypadku L1/L2 wymaga tylko dopisania do listy checks, nie zmiany logiki raportu. EXP opisuje pokrycie (co realnie mierzymy) i luki (co nadal wymaga vendor data / M5/M6).
  - Stop: nie symulować PASS przez pomijanie walidacji; jeśli L2 wymaga stock zlib 1.3.1 do byte-identical i runner ma zlib-ng, check jest `SKIP (zlib-ng, H9)` z linkiem do uzasadnienia. Po 2 nieudanych próbach ustabilizowania bez zmiany semantics — `blocked` + EXP.
  - Claims: C-2760–C-2769

- [ ] **H27 — Raport postępu L1–L4 (dashboard): reader-coverage + wyniki CI jako artefakt**
  - Status: open · Owner: — · Critical: yes
  - Depends: H25, H26
  - Goal: jeden widok pokazuje postęp celu „karta SD czytana przez auto”, nie jako procent coverage kodu, lecz jako stan warstw: L1/L2 (offline, runnable), L3 (ile targetów PASS/BLOCKED/SKIP, które readery mają VA), L4 (S0–S3: planowane/wynik z EXP/protokołu). Źródłem prawdy pozostają `docs/research/reader-coverage.md`, `claims.md`, `TODO.md` i wyniki narzędzi — dashboard je agreguje.
  - Precheck: istnieją `docs/research/reader-coverage.md`, `tools/l3check.py --help`, `tools/l3_harness/targets.json`; workflow H25/H26 produkuje lub może produkować JSON. Jeśli format któregoś wejścia jest niestabilny, najpierw zdefiniować minimalny kontrakt (osobna sekcja w EXP) zamiast parsować heurystycznie.
  - Scope: narzędzie (nazwa ustalona, np. `tools/progress_report.py` z `--selftest` na syntetycznych danych) lub skrypt workflow generujący `progress.{json,md}`: tabela L1/L2 z ostatniego runu, tabela L3 z `l3check --json` (domyślnie `--build-corpus`; bez vendor firmware jeśli niedostępne), podsumowanie reader-coverage (ile wierszy: writer none/partial/exists, reader unlocated/partial/located, L3 —/blocked/pass), sekcja L4 jako jawny status ręczny (`NOT RUN`/wynik Sx) linkujący do M6/M5 tasków — bez automatycznego PASS. Wynik jako GitHub Actions job summary + artefakt; opcjonalnie commitowany snapshot tylko jeśli bezpieczny (brak vendor danych) i uzgodniony osobno. **Poza zakresem:** GitHub Pages, zewnętrzny serwis, modyfikacja `reader-coverage.md` bez dowodu.
  - Input: `tools/l2check.py --json` (tam gdzie użyte), `tools/l3check.py --json`, `docs/research/reader-coverage.md`, `docs/research/card-test-plan.md` (L4 kontekst).
  - Done when: artefakt z PR/main jasno rozdziela „udowodnione offline”, „udowodnione przez firmware/L3”, „wymaga auta” i nigdy nie podnosi L2 do L3/L4; `--selftest` narzędzia raportu działa bez vendor danych. EXP z przykładowym wydrukiem i mapowaniem pól na regułę 13.
  - Stop: jeśli `reader-coverage.md` nie daje się wiarygodnie zparsować bez zmian semantycznych, raport opiera się na jawnej, małej tabeli pośredniej generowanej/utrzymywanej z kontraktem — decyzja w EXP; nie zgadywać statusów.
  - Claims: C-2770–C-2779

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

- [ ] **H29 — L4 (hardware/Marek): automatyzacja przygotowania artefaktów i rejestracji wyników S0–S3**
  - Status: open · Owner: — · Critical: no
  - Depends: H27, M5.13b (S1/S2 istnieją), M6.2/M6.5–M6.7 (protokół)
  - Goal: L4 nie da się zautomatyzować w GHA (wymaga auta), ale da się zautomatyzować przygotowanie paczki testowej i powtarzalną rejestrację wyniku, żeby postęp L4 był widoczny w tym samym systemie co L1–L3.
  - Precheck: `docs/research/card-test-plan.md` i taski M6.2/M6.5–M6.7 opisują S0–S3; `tools/imgpatch.py`/artefakty S1/S2 są dostępne tam, gdzie budowane (vendor data poza repo). Sprawdzić aktualny stan: M5.13b done, bench czeka na Marka.
  - Scope: (1) `workflow_dispatch` „prepare-L4-bundle” (lub narzędzie) przyjmujący ścieżki/artefakty dostarczone poza repo lub budowane na self-hosted runnerze z dostępem do vendor data: generuje manifest (SHA-256 obrazów, diff zakresów jak w M5.13b, wersja narzędzi, profil/test id), checklistę S0–S3 i szablon wyniku (PASS/FAIL/objaw, zdjęcie/serial/log opcjonalnie) — bez commitowania obrazów. (2) Szablon EXP/issue lub `docs/experiments/` snippet do wklejenia wyniku Marka tak, by H27 mogło policzyć L4 jako `Sx PASS/FAIL/NOT RUN`. **Poza zakresem:** zdalne sterowanie autem, automatyczny werdykt L4, przechowywanie obrazów kart w repo/artefaktach publicznych.
  - Input: `docs/research/card-test-plan.md`, M6.2/M6.5–M6.7, H27 format raportu, `tools/imgpatch.py` metadata.
  - Done when: da się jednym poleceniem/workflow wygenerować kompletną paczkę „co nagrać na kartę + co sprawdzić + gdzie wpisać wynik”, a wynik L4 da się odczytać maszynowo przez H27 bez interpretacji prose. EXP z przykładowym bundle manifestem (syntetyczne ścieżki/hashe przykładowe, nie vendor).
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
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M8.E1b verified the VAs; M1.2a/M1.2d frame the payload)
  - Goal: decode every `IMAGE_SCN_COMPRESSED` section without QEMU. M8.E1b
    ended the address question; what is missing is the codec inside
    `0x8803a384`, not the entry point. **Sixth pass: this is the single gate
    for the software side** — M3.2b and M3.11 both ended at "the reader is in
    Navi.exe sec1", so M9.10 and M9.12 wait here too.
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
  - Re-opens on merge (rule 15): **M3.2b, M3.11, M3.13, M9.10** and the
    precheck-gated **M3.14–M3.16, M3.18**; M1.3/M1.4 follow directly. Put the
    re-open in the same commit as the `done`.
  - Claims: C-2360–C-2369

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
  - Status: open · Owner: — · Critical: yes
  - Depends: — (**M9.6 merged** `ff8720d`, M2.15 and M2.3 done); the corpus and
    the comparator are both on `main` now
  - Note (sixth pass): the old blocker ("firmware verdicts need the L3 target,
    unavailable offline") was **wrong** — M9.6 runs the comparator offline with
    a stubbed `KernelIoControl(0x0101302C)`, and M2.15 supplied the exact card
    bytes plus the `+96`/`+112`/`+114` unit fields. Only M9.6 is missing.
    The offline model-M0 gives 66 ACCEPT / 23 DIFFERENT
    (EXP-2026-11-06-M2.4-hddinfo-variants).
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
  - Status: open · Owner: — · Critical: no
  - Depends: — (the census and checker are in `tools/rd_restrictions.py`, M4.23)
  - Goal: decode the unit-1 layout of the odd records that `rd_restrictions.py census` reports as mismatched (mark word, node blocks, entry words, side words).
  - Precheck: `python3 tools/rd_restrictions.py census` on `B28R070R.DAT` and `LEV3456R.DAT` reproduces the part-b notes in EXP-2026-11-08-M4.23.
  - Scope: odd records of `0x2046` (B28R070R level 2) and `0x03e4` (LEV3456R level 5); no writer.
  - Input: EXP-2026-11-08-M4.23-restriction-encoding (part-b table), `tools/rd_restrictions.py` (`part_b_check`).
  - Done when: a parser reproduces every odd record of those two tiles (76 + 34 pairs) word for word, with its own `--selftest`, and the mark and side words are explained by the parent record, not fitted.
  - Stop: after two rounds of fitting without a full match, record a negative EXP and stop.
  - Claims: C-2880–C-2889 (was C-2630–C-2639, collision fixed by H23)

- [ ] **M4.25 — Regulation-word test: the no_* turns without a from-word, and the only_* encoding**
  - Status: open · Owner: — · Critical: no
  - Depends: — (M4.23 tool)
  - Goal: explain why most `no_*` to-entries carry no from-word (`rd_restrictions.py match`: 152/411 and 128/235) and find the `only_*` encoding.
  - Precheck: `match --level 1` and `--level 2` on B48R058R reproduce 152/411 and 128/235.
  - Scope: B48R058R only; OSM side from the IMF; no writer.
  - Input: EXP-2026-11-08-M4.23-restriction-encoding (observations 12–13), the entry-class table of `match`.
  - Done when: each miss class is explained by a named, counted mapping check, or the same test passes (pre-stated PASS) on a second tile, or a negative EXP records it.
  - Stop: after one mapping audit and one second tile; otherwise `blocked` with the EXP.
  - Claims: C-2910–C-2919 (was C-2640–C-2649, collision fixed by H23)

- [ ] **M4.26 — Firmware reader VAs for section-2 grid kinds; LEV3456R level-4/5 parcel addressing**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: locate the reader of grid-tile section 2 (kinds `0x1046`/`0x2046`) and the consumer of the regulation words; find the parcel addressing of LEV3456R levels 4 and 5 (the writer's `clarion_bg.parcel_code` reproduces none of the 414 codes).
  - Precheck: `python3 tools/sh4xref.py` on the first 256 MiB of `archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` (image start `0x200200`) reproduces the RGD_DATA callers `0x00426cfc`, `0x00427870` of `docs/format/map-tiles.md`.
  - Scope: Navi.exe build A via `tools/cerom.py`; callers of RGD_DATA and MAP_DATA only, no new disassembly campaign.
  - Input: `docs/format/map-tiles.md` section table; C-870–C-872, C-887; EXP-2026-11-08-M4.23-restriction-encoding (observations 14–15).
  - Done when: a VA per kind (or UNKNOWN with a negative EXP), and a parcel-code function that reproduces every LEV3456R level-4/5 code.
  - Stop: after the RGD_DATA callers are traced; otherwise `blocked`.
  - Claims: C-2800–C-2809 (was C-2650–C-2659, collision with M1.15/M5.22/M5.23 fixed by H23)

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
  - Depends: — (**not** M1.2f: no executable section of build A is compressed,
    C-2128)
  - Re-opened (ninth pass, 2026-11-08). The pass-1 blocker — "the caller lives
    in `Navi.exe` sec1, uncompressed code we cannot read" — is **refuted**:
    sec1 flags `0xc8002040` (`.data`) and every executable section is readable
    (C-2128/C-2129). What remains true is "no *static* caller of
    `fn 0x41c7e8`", which is the shape that hid the POINT walker: an
    **indirect call through a pointer in `.data`**, or a caller in a module the
    search never named. Re-run with `tools/sh4scan.py` (constant/mask
    signatures, builds A **and** B/C) plus an L3 probe: hook `0x41c7e8` and
    record the caller PC. The chunk engine is already usable for S1 (M9.11).
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
  - Result: EXP-2026-11-06-M3.2b-cmp-chunk-reader-inflate.md (partial). zlib
    found in uncomp sec0 of 6 A modules (not compressed); Navi.exe inflate API +
    wrapper `0x542148` + chunked decompressor `fn 0x41c7e8` recorded (no seek/no
    `78 9c` scan/no `0x10000` compare in that layer). `chunk_offset[]` consumer
    not in uncompressed code (positive controls); likely Navi.exe comp sec1/sec2.
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
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M3.11b only for the final L3 run)
  - Goal: the function that turns a `POINT` record (record 0 of US page
    `0x840ba0`: `60 40 8f 9c …`, name `HANA HEALTH CENTER4590@HANA HWY` at
    `+0x5e`) into the name string the UI shows — VA, args, output.
  - Precheck: `sh4xref --to 0x3ceac` hits `fn 0x003a03b4` (the dump).
  - Scope: Navi.exe sec0, functions reachable from `0x003cd910`,
    `0x003d1150`, `0x003d1188`, `0x003cc93c`, `0x003f5c40`, `0x003f6220`, and
    the other `0x3ff` sites in `0x3f5900–0x3f9400`.
  - Input: C-2544 (SDL chain), C-2545 (offset mismatch). Leads: (1) is
    `rec+4+14` / `rec+4+21` in the **swapped** record the name length/text?
    In native order record 0's bytes pair-swap; check `rec[18]`/`rec+25`
    after `swap16`. (2) The body has sub-records (`02 40 03 02`, `09 54 …`,
    `28 ff …`): maybe `0x3cc93c` walks them with the same u16 header — try
    `0x3f5194` on `rec+4`. (3) `refer.md`'s per-file field dictionary
    ("facility name 111" bits): look for a bit-field reader taking a bit
    offset. (4) Run `0x003d1150` in PySh4 on record 0 (raw and swapped) and
    print what `*ptr` points at.
  - Done when: PySh4 run of the accessor on record 0 returns
    `HANA HEALTH CENTER` (length + pointer or copied buffer), and on the
    M5.12 renamed page `OSM2LEAF TEST POI1`; `firmware.md` records VA/args.
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
  - Status: open · Owner: — · Critical: yes
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
  - Result: `EXP-2026-11-06-M3.13-addre-reader.md` (C-2180–C-2183). ADDRE confirmed on same REFER001 family mechanism (`0x14e8`→`REFER001`+`INDEX003.DAT`, `0x003fbed8`/`0x0040b358`/`0x004125a8`, `fn 0x0040114e` resolves `ADDRE0`); no parser VA in uncompressed code; `refer.md`/`firmware.md` updated with access path and blocked grammar-field→instruction table.

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
  - Status: open · Owner: — · Critical: no
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

- [ ] **M3.18 — `ICADM0nn` / `ZIPFR001` readers (H11 G2)**
  - Status: open · Owner: — · Critical: no
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

- [ ] **M3.20 — Name the register-AND mask variant; correct the M3.11 pattern text**
  - Status: open · Owner: — · Critical: yes
  - Depends: M3.19
  - Goal: M3.11 §2 reports `and #0x70,r0` then `cmp/eq #0x60` as 1 hit in build
    A. The one site is `mov #0x70,R3; and R3,R0; cmp/eq #0x60,R0`
    (Navi.exe `0x3715c8–0x3715cc`), a register AND that the immediate pattern
    cannot match (EXP-2026-11-08-M3.19-sh4scan §5).
  - Precheck: `python3 tools/sh4scan.py IMG --image-start 0x200200 dump --module Navi.exe --va 0x3715c0 --count 8`
    shows those three halfwords.
  - Scope: `tools/sh4scan.py` only (a `mask-pair --via-reg` variant, stdlib,
    with a synthetic self-test); build A uncompressed sections; no other task's
    lines.
  - Done when: `mask-pair --via-reg --cmp 60` runs on `IMAGE_START 0x200200`,
    its selftest pins the variant, and M3.11's pattern text is corrected by a
    new claim row (no deletion, per the ledger rules). The count is the result,
    not a precondition: report whatever it is.
  - Stop: if the variant count is not 1, record it in an EXP and stop.
  - Claims: C-2560–C-2569

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
  - Status: blocked · Owner: claude/m4.8b-transform-proof · Critical: yes
  - Blocker: the local-scale clause cannot be answered from packed POI ids
    (no sub-unit field decoded); origin 52742 and the 16-POI list are met,
    but "within a few metres" is not (median 3.6 km).
  - Unblock: M4.8d (sub-unit POI/ADDRE field).
  - Result: EXP-2026-11-08-M4.8b-transform-proof.md (16 POIs, origin 52742
    fits longitude, latitude bias +2.8 km unexplained).
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

- [ ] **M4.8d — Sub-unit field for POI/ADDRE positions**
  - Status: open · Owner: — · Critical: no
  - Depends: —
  - Goal: find a sub-unit position field in `POINT`/`ADDRE` records (a
    `0..2047`-class local value) so M4.8b can test local scale 1 vs 2.
  - Done when: the field is decoded (or `UNKNOWN` with the method) and the
    local-scale test is in an EXP that re-opens M4.8b.
  - Claims: C-2930–C-2939 (was C-1908–C-1909, overlap with M4.8b fixed by H24)

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

- [x] **M4.12 — `COORD001`/`ZCODE`/`ICODE001` remaining fields**
  - Status: done · Owner: task/m4.12-coord-zcode-icode-fields · Critical: no
  - Depends: —
  - Goal: `COORD001` `level`, the `ZCODE` offset base, `ICODE001` trie roots.
  - Done when: each is decoded with a test, in `coord-zcode-icode.md`.
  - Claims: C-1000–C-1009
  - Result: COORD001 `level` = 48-bit region bitmask `M=(level_u32<<16)|pad_u16`, one-hot `0x400000000000>>(i-1)` for non-last, last `level_u32==guard` (EU 33/US 11, verified). ZCODE: form A (018/033) offset base = ADDRE `unaddr(rec_addr_enc@0x1012)`, trie `crec` @0x1100 halfword-indexed, 16B recs (ZCODE018 rec0 verified); form B (31 files) `>HHBBHI` dir+ladder, no uniform offset base (OBSERVED). ICODE001 ISO header `>HH(hw,countries)`, 7 EU + 2 US per-language country-chain root byte offsets located by chain tracing; root-pointer index table not found. `tools/coord_zcode_icode.py` (--selftest + --verify-*), EXP-2026-11-06-M4.12-coord-zcode-icode-fields, C-1000–C-1009.

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
  - Status: blocked · Owner: claude/m4.16b-record-framing · Critical: yes
  - Blocker: the C-884 walk is not reproducible offline: `sh4dis.py` lacks MOVT/SHAR/SHLD/SHAD used in the walk and accumulator, and schema table `0x00d53500` is undecoded.
  - Unblock: M1.11c (then a directory-walk task; the join itself stays with M4.16d).
  - Result: EXP-2026-11-08-M4.16b-record-framing — gate passed (five functions plain in Navi.exe sec0; callees verified); walk not run; done-when not met (negative).
  - Depends: M4.15
  - Goal: reproduce the per-record length/offset directory walk from bytes to
    recover true TMC field boundaries, then re-run `tools/rdstm_place.py` on
    decoded fields (location/area/front/rear/inter-section).
  - Done when: ≥20 decoded records map to tile/mesh/coordinates with a named
    join key and ~0 random-key control, or the mapping is proven impossible
    with method recorded.
  - Claims: C-2300–C-2309 (was C-1840–C-1849, a collision with M5.1b)

- [ ] **M1.11c — `sh4dis.py`: MOVT, SHAR, SHLD, SHAD opcodes**
  - Status: open · Owner: — · Critical: no
  - Depends: M1.11 (done)
  - Goal: decode the dynamic and single-bit shift opcodes and `movt` that the
    RDSTM directory walk (`0x003f56bc`, `0x003f5e10`) uses, so an offline walk
    can be run faithfully (M4.16b unblock).
  - Done when: `sh4dis.py --selftest` pins the four encodings (`0x0n29`,
    `0x4n21`, `0x4n0d`, `0x4n0c`) and a real-image window shows no undecoded
    opcode at the five M4.16b addresses; EXP recorded.
  - Claims: none reserved yet; take the next free range in `claims.md` when claimed.

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
  - Status: open · Owner: — · Critical: no
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

- [ ] **M4.28 — Explain the POI latitude residual (+2.8 km) on a known entrance**
  - Status: open · Owner: — · Critical: no
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

- [ ] **M4.29 — `class_code` second-country / non-motorway control (M4.17 follow-up)**
  - Status: open · Owner: — · Critical: no
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

- [ ] **M4.30 — Restriction word-test deepening: class-dependent encoding and mapping errors (M4.23 follow-up)**
  - Status: open · Owner: — · Critical: no
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
  - Blocker: the uncompressed-files exact scan never finished, so the EXP has no list of every hit outside the compressed pages; the Done when is not met.
  - Unblock: — (re-run the scan in EXP-2026-11-08-M5.12c-poi-copies Method 3 and record the hits).
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

- [ ] **M5.16 — `LEV3456R.DAT` generator: levels 3–6 from OSM (H11 G4)**
  - Status: open · Owner: — · Critical: no
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
  - Claims: C-2400–C-2409

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

- [ ] **M5.25 — Reconcile REFER POI page encoding (slot_budget vs mutate_refer_poi/M5.12c)**
  - Status: open · Owner: — · Critical: yes
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
  - Claims: C-2870–C-2879 (was C-2750–C-2759, collision with H25 fixed by H23)

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

- [x] **M8.A1 — Build env** `tools/qemu-ze0/build.sh`: pinned QEMU (≥ 8.2),
  patch, `--target-list=sh4-softmmu`. Done when `qemu-system-sh4 -M ze0`
  lists the machine. Status: done · Owner: session-ZMxuBT · Depends: —. Claims:
  C-1230–C-1239
- [ ] **M8.A2 — Machine skeleton** `hw/sh4/ze0.c`: `sh7785`, RAM at phys
  `0x08000000` (128 MiB), P1/P2 aliases, unimplemented-device catch-all over
  `0xff800000`–`0xffffffff` and areas 4/6, `select SH4_CCN` with
  `sh4_ccn_iomem()` at `0xff000000` and `sh4_ccn_arrays()` at `0xf0000000`,
  and one `ze0-stubs` instance.
  - Status: open · Owner: — · Critical: yes
  - Depends: — (M8.A1, M8.A4 and M8.A5 are merged)
  - Note (PM 2026-11-06): the three series were never built together. M8.A1 saw
    `m8a4-0002/0003` rejected on 8.2.7; M8.A4/M8.A5 report them applying (the
    0003 banner says "Base: QEMU 8.2.7"). One clean `build.sh --force` over
    `patches/*.patch` settles it — record the resulting patch order.
  - Done when: `bash tools/qemu-ze0/build.sh --force` applies every patch,
    builds, and `qemu-system-sh4 -M help` lists `ze0`; `-M ze0` reproduces the
    `ce_qemu_probe.py` access list; the run log and the final patch order are in
    the EXP.
  - Claims: C-1240–C-1249

- [ ] **M8.A3 — Built-in loader** (`kernel=0x3e00200`, `app=0x200200`):
  parse `ECEC`/`ROMHDR`, copy B/C and A to `physfirst & 0x1fffffff`, PC =
  `nk.exe` entry. Done when booting needs no `-device loader`. Status: open
  · Depends: M8.A2. Claims: C-1250–C-1259
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
- [ ] **M8.A6 — Debug serial** (`sh_serial` at `0xffe46000`; writer
  `0x8804cfa4`, pointer at `0x8804ce78`). Done when the CE boot banner
  appears or an EXP shows why not. Status: open · Depends: M8.A2. Claims:
  C-1280–C-1289
- [x] **M8.A7 — Trace tooling** `tools/qemu-ze0/run.sh` (logs, gdbstub,
  `summarize_log`, gdb script printing thread list + current module).
  Depends: —. Claims: C-1290–C-1299
  Status: done · Owner: session-ZMxuBT. Result: `run.sh` (machine select,
  log+summary, timeout, dry-run) and `gdb-ze0.py` (PC->module, 30 checks);
  stand-in QEMU only (EXP-2026-11-06-M8.A7-trace-tooling).
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
  - Status: open (VA/prototype verified by M8.E1b; runtime decode pending) · Owner: — · Critical: yes
  - Depends: M8.E1b (VAs verified, C-2290–C-2293). Does **not** need F1: call
    the function under `-M none` + gdbstub with RAM-only state (LE SH-4).
    M8.A1 now builds a LE `qemu-system-sh4` from the pinned 8.2.7 tarball, so
    the toolchain half is done. M1.2f is the parallel Python route to the same
    two vectors — whichever lands first unblocks M1.3/M1.4.
  - Note: M8.E1's initial "VA refuted" blocker was a BE endianness artifact,
    corrected by M8.E1b (C-1600/C-1603 superseded). Verified entries (LE):
    `DECOMP_WRAP 0x88037590` / `DECOMP_SECT 0x88037464` (core framing) /
    `DECOMP_BLK 0x8803a384`, loader flag test `0x88038666` in `fn 0x880385e4`.
    Use `qemu-system-sh4` (LE). DECOMP_WRAP needs kernel lock/context stubs
    (C-2293); calling SECT with an initialised frame may bypass that.
  - Result: EXP-2026-11-06-M8.E1-rom-decomp-tool (corrected by M8.E1b).
    QEMU+gdbstub framework `tools/cedecomp_run.py` (LE-updated) ready.
    EXP-49 runtime decode **not yet achieved** (LE QEMU + kernel-context
    stubs/bypass, C-2294). All-245/FILESentry not run.
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
  - Status: blocked · Owner: claude/m9.6-mapcode-compare · Critical: yes
  - Blocker: `origin/main` runner has no `entry.kind = "module"` to call
    `fn 0x03bd2ad8` at its VA; that plumbing is M9.20 (PR #89, draft).
    Negative EXP: EXP-2026-11-08-M9.6-mapcode-compare.
  - Unblock: M9.20 (re-open M9.6 when it merges; then run the done-when check).
  - Depends: — (M9.5, M2.5 done; M2.15 helps; M9.20 for the module entry)
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
- [x] **M9.9 — Keep `l3-ghidra.md` "How to use L3" current.** Done with each
  M9 PR (no separate claim needed). Status: done · Owner: session-ZMxuBT.
  Done: current commands, statuses, targets
  and the seven-step reader procedure (EXP-2026-11-06-M9.9-l3-docs).

- [ ] **M9.10 — L3: decode the US POI with the firmware's own reader (software S2)**
  - Status: open (walk part runnable; name part waits for M3.11c) · Owner: — · Critical: yes
  - Note (2026-11-07): the old blocker ("walker in compressed sec1") was wrong
    (C-2128/C-2129). The walker `0x003f5194` already runs on the factory page
    via `tools/point_walk_l3.py walk` (C-2541). Port that into a
    `poi_record_walk` target now; add the name check when M3.11c names the
    accessor. Feed the page in the byte order M3.11b finds (until then:
    `swap16`, stated as an assumption).
  - Depends: M3.11c (name), M3.11b (byte order), M9.5 (M9.21 is done)
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

- [ ] **M9.11 — L3: the firmware's chunk decoder on our recompressed `.cmp` (software S1)**
  - Status: blocked · Owner: claude/m9.11-chunk-decoder · Critical: yes
  - Unblock: M9.11b (runner entry kind that calls the firmware chunk reader; fills `cmp_ind_reader`).
  - Blocker: the firmware path passes on the factory, S1 and S2 pairs and on both controls (page `0x840ba0` byte-identical, corrupt `.ind` rejected, swapped `+4`/`+8` fails); `targets.json` `cmp_ind_reader` cannot be filled because `runner.py` has no firmware-call kind. The sec1 table that inflate reads (`0x574de0`, `inflate_mask[17]`) is supplied from public zlib source, see EXP.
  - Result: EXP-2026-11-08-M9.11-chunk-decoder (firmware path PASS; target registration open).
  - Depends: M9.5, M5.13b (the S1 pair). M3.2b is **no longer** a dependency.
  - Goal: prove in software what S1 would prove in the car: the firmware's own
    zlib + chunk loop accept our recompressed bytes and return the same
    logical page. Re-scoped in the sixth pass: `fn 0x41c7e8` (M3.2b, C-2063)
    takes its 20-byte-stride chunk table from the caller, so the harness can
    build that table from `.ind` and never needs the `.ind` parser that lives
    in `Navi.exe` compressed sec1.
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
  - Claims: C-2150–C-2159

- [ ] **M9.11b — L3 runner: a firmware-call target kind for the chunk reader (fills `cmp_ind_reader`)**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.11 (firmware path and sec1 table provenance, EXP-2026-11-08-M9.11-chunk-decoder), M9.5 (done).
  - Goal: let `runner.py` run a firmware function with memory setup (the 20-byte table,
    the stubs, the sec1 `inflate_mask` table as a named, sourced input), so that
    `targets.json` `cmp_ind_reader` runs the chunk reader on a corpus pair through the runner.
  - Input: `tools/chunk_decoder_l3.py` `run_firmware` and its stubs; `tools/l3_harness/runner.py`
    entry kinds (`module` passes register arguments only); `targets.json`.
  - Done when: `runner.py run cmp_ind_reader` on the factory pair reports PASS and exit 0; the
    corrupt-`.ind` and swapped-field cases report as the controls in EXP-2026-11-08-M9.11-chunk-decoder; the sec1 table
    is a declared input of the entry (not a silent default), and `runner.py selftest` passes.
  - Claims: C-2940–C-2949 (was C-2157–C-2159, overlap with M9.11 fixed by H24)

- [ ] **M9.12 — `l3check.py --card`: the software gate before any car test**
  - Status: open · Owner: — · Critical: yes
  - Depends: M9.11 (runnable now), M9.10 (blocked — the first run reports the
    POI reader as "not yet available"), M9.6, M9.8 (tool skeleton)
  - Goal: one command that a card image must pass before Marek puts it in
    the unit: run every available L3 target (map-code compare M9.6, `.cmp`
    reader M9.11, POI reader M9.10, later tile reader) on the files that
    differ from the factory image.
  - Done when: `l3check.py --card OUT.img --factory IMG` lists per target
    pass / fail / not-yet-available, exits non-zero on a fail, and the EXP
    shows it on S0 (all pass), S1 and S2.
  - Claims: C-2160–C-2169

- [ ] **M9.13 — L3 target `tile_reader` on factory and generated tiles**
  - Status: blocked · Owner: claude/m9.13-reader-run · Critical: yes
  - Unblock: M9.20 (module entry kind, `engine_hook`; PR #89).
  - Blocker: `runner.py` accepts only `synthetic`/`blocked` entry kinds, so the M3.5 reader VA cannot be run; `tile_reader` still reports BLOCKED. See EXP-2026-11-08-M9.13-reader-run.
  - Depends: M9.5 (M3.5 reader VAs `0x0041f26c`/`0x004259bc`/`0x0042757a`; M3.6 helps)
  - Goal: the tile is the core generated format; run the firmware's tile
    reader on it. Fills `tile_reader` (now `blocked`) in `targets.json`.
  - Done when: the reader returns the same level table / section offsets as
    `clarion_tile.read_tile` for one factory tile and for the M4.4 one-vertex
    tile; later for an M5.4 generated tile.
  - Claims: C-2230–C-2239

- [ ] **M9.14 — L3 target `drstr_parser`**
  - Status: blocked · Owner: claude/m9.14-reopen · Critical: yes
  - Re-opened (ninth pass, rule 15): **M9.20 merged** (`562215a`) with the
    module entry kind and `engine_hook`, so the first blocker no longer holds.
    The reopened run (EXP-2026-11-08-M9.14-reopen) ran the module entry on the real head image:
    the reader's data is in compressed `sec1`, so it stops at once.
  - Depends: M3.10, M9.5 (both done)
  - Done when: the firmware parser accepts the factory `DRSTR001.DAT` (EU and
    US) and one rebuilt by M5.6, and rejects one corrupted case, recorded.
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

- [ ] **M9.17 — L3 target `mmain_reader` (H11 G1)**
  - Status: blocked · Owner: claude/m9.17-reopen · Critical: no
  - Re-opened (ninth pass, rule 15): M9.20 merged (`562215a`); the module-VA
    entry it needs now exists.
  - Blocker: the M3.8 reader runs as a module entry (M9.20) but its first data access is at `0x0055d040`, in `Navi.exe` section 1 (compressed, `rw-`), which the map skips: `BLOCKED` UNMAPPED.
  - Unblock: M1.2f (port `DECOMP_BLK`, so section 1 can be mapped).
  - Result: EXP-2026-11-08-M9.17-reopen (negative: module run BLOCKED at a compressed `.data` access, controls PASS; C-2372–C-2373). Earlier block: EXP-2026-11-08-M9.17-m38-reader (C-2370–C-2371).
  - Depends: M9.5 (M3.8 located the reader)
  - Goal: `MMAIN001.DAT` is the only generated file whose reader is located
    and whose L3 target does not exist.
  - Input: reader `0x0041a438` (open `0x0041b780`, read `0x0041b954`, exactly
    `0x1000` bytes, no label/count check — C-1780–C-1789); the factory
    `MMAIN001.DAT` (EU and US); a `mmain_reader` entry in `targets.json` and a
    `corpus.py` row.
  - Done when: the target runs and returns the `0x1000`-byte read for the
    factory file and for a rebuilt one, rejects a 4095-byte file, and matrix
    row 3 carries the L3 result.
  - Claims: C-2370–C-2379

- [ ] **M9.18 — L3 targets for `LEV3456R` and the tile sections (H11 G8)**
  - Status: open · Owner: — · Critical: no
  - Depends: M9.13 (matrix rows 18–20)
  - Goal: `tile_reader` covers `B28R070R` only; the coarse database and the
    section-4 consumer have no L3 target at all.
  - Input: the `LEV3456R` filename load `0x0040a014`, M3.6's section answers,
    `lev3456.py`, `section4.py`, `targets.json`, `corpus.py`.
  - Done when: the coarse-level reader and the section-4 consumer return the
    same records/name list as the Python tools for one factory tile and one
    generated tile, and rows 18–20 carry the verdicts.
  - Claims: C-2440–C-2449

- [x] **M9.20 — L3 plumbing: firmware entry kind, `engine_hook`, `ghidra/l3_run.py`**
  - Status: done · Owner: claude/m9.20-l3-plumbing · Critical: no
  - Depends: —
  - Goal: the M9.5/M9.9 follow-ups that stop a real reader from running even
    when M3 has found its VA.
  - Input: EXP-2026-11-06-M9.5 (`entry.kind = "module"`), EXP-2026-11-06-M9.3
    (`StubDispatcher.engine_hook(target)` reading r4–r7), EXP-2026-11-06-M9.9
    (`tools/l3_harness/ghidra/l3_run.py`, README refresh), `targets.json`,
    `runner.py`, `tools/README.md`.
  - Done when: `runner.py run` can call a function at a module VA without a
    hand-built `-device loader` map, the stub dispatcher exposes argument
    registers to a target handler, the Ghidra back end has one documented
    entry script, `tools/l3_harness/README.md` and `tools/README.md` match the
    code, and the L3 selftest covers all three.
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
  - Input: `tools/l3_harness/engine.py` (`_load`/`_store`/`_fetch`,
    `cmp/str`, the `bt/s`/`bf/s` refusal), SH-4 manual for the delay-slot
    rule; `point_walk_l3.le_engine()` as the reference.
  - Done when: `PySh4(endian="little")` (default unchanged for the existing
    self-tests), `bt/s`/`bf/s` modelled with a self-test vector each,
    `point_walk_l3.py` uses it instead of its subclass, and `0x3f39c0` runs
    on the US page with the globals `0x00d5e4e4`/`0x00d5e4d0` set.
  - Claims: C-2550–C-2559
  - Result: EXP-2026-11-08-M9.21-pysh4-le; `PySh4(endian="little")` and
    `bt/s`/`bf/s` in `tools/l3_harness/engine.py`; `0x3f39c0` runs on the US
    page with the globals set and matches `parse_page` (C-2550–C-2557).

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

- [ ] **M9.24 — Module entries that call coredll file APIs: bind imports, stub the CRT file calls**
  - Status: open · Owner: — · Critical: yes
  - Depends: M1.2f (`sec1` of `Navi.exe` must be decompressed first)
  - Goal: `runner.py` writes stub VAs into the module's COREDLL import slots
    (`0x0055d000`+ in `sec1`), models coredll `fopen`/`fread`/`fseek`/`ftell`/
    `ferror`/`clearerr`/`fclose`/`_modlu`/`wcstombs`/`strncat`, and models
    stack arguments for module entries, so `sub_00419350` (and its caller
    `0x00419684`, which reads above the stack top) runs on a file. Ordinals
    come from M3.10 and must be re-derived first (`cerom.py exports coredll`
    raises `KeyError` on this image). Input: EXP-2026-11-08-M9.14-reopen.
  - Done when: `runner.py run drstr_parser` on the EU factory `DRSTR001.DAT`
    returns a verdict or a named blocker with the faulting PC, and a
    `verdict_map` is written from the decoded return codes (not guessed).
  - Claims: C-2640–C-2649

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
