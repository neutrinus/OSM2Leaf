# AGENTS.md

Research repo for generating Nissan Leaf ZE0 (2011–2012) navigation maps from
OpenStreetMap. **Research only** — nothing here is validated in a car, and
hardware access is currently unavailable. All repo content (code, docs,
commits) is English; conversation may be Polish.

## Where the truth lives

| Question | File |
| --- | --- |
| Is this fact established? | `docs/research/claims.md` — canonical ledger, trust it over prose |
| What does this format look like? | `docs/format/*.md` — living pages |
| What is being done now? | `TODO.md` — the board, rules 1–17, task blocks |
| Can the firmware read our file? | `docs/research/reader-coverage.md` — 30-row matrix |
| What was tried and why did it fail? | `docs/experiments/EXP-*.md` — append-only |

Evidence flow: `format doc → claim ID → EXP record → tool command`. A claim
without a reproducible command is a hypothesis; mark it so.

## Taking a task (parallel agents)

~15 agents work from `TODO.md` at once. The full rules are in `TODO.md`
("How to take a task"); the ones that get broken:

1. Pick an `open` task whose `Depends` are `done` and whose ID appears in no
   open PR title. Check this **right before claiming**, not from an old view:
   `git fetch origin`, read the task line on `origin/main` (not your
   worktree's copy), and list open PRs (`gh pr list --state open --search
   "[ID]"`) and the claim blocks in use.
2. **First commit claims it**: change only your task's line to
   `Status: in progress · Owner: <branch>` (`tools/board.py claim ID --owner <branch>`), then `git push -u origin <branch>`
   before any other work, and open a draft PR `[ID] short title`. An unpushed
   claim is invisible: a claim edited in a worktree exists only on your disk,
   other agents read `origin` and open PRs. The claim commit holds the claim
   alone (no task work), and the push and draft PR follow it within a minute
   of creating the worktree. Read, plan and code only after the draft PR is up.
3. One task per PR; touch only your task's files, your EXP, your claim rows.
4. **Last commit**: the work plus `Status: done`, `[x]` and a `Result:` line
   naming the EXP. `done` requires the task's own `Done when` check to pass —
   if it did not, the status is `blocked`, never `done`.
5. **Merge to `main` yourself** (a task is done only when its commits are on
   `origin/main`), delete the branch, close leftover drafts. Never force-push
   `main`.
6. Blocked is a result: `Status: blocked` + a one-line blocker + `Unblock:`
   naming the task that re-opens it + a negative EXP. When the unblocking task
   merges, its PR sets you back to `open` (rule 15).

## Editing `TODO.md` and `claims.md`: use `tools/board.py`

Never rewrite these two files with an editor or a model, and never paste a
whole copy back after a conflict: PR #340 replaced the last 787 lines of
`TODO.md` and 324 of `claims.md` with an older copy (42 task blocks and 199
claim rows gone) and every checker passed. `tools/board.py` changes one
splice and refuses a write that drops a task or claim ID or moves the line
count by more than its own edit (H123).

```bash
python3 tools/board.py claim M9.12 --owner task/m9.12-slug     # rule 2: the claim commit
python3 tools/board.py done M9.12 --result "EXP-…; 14/14"       # rule 4: [x] + done + Result
python3 tools/board.py block M9.12 --blocker "…" --unblock M1.2f --result "EXP-… (negative)"
python3 tools/board.py field M9.12 Note "…"                      # set one field
python3 tools/board.py next-id M9 && python3 tools/board.py next-claims
python3 tools/board.py add-task new-task.md                      # appended to its stream
python3 tools/board.py add-claims --section "M9.12 — …" --create --file rows.md
python3 tools/board.py claim-status C-2149 RETRACTED
python3 tools/board.py archive M1.2e M3.19 --to docs/research/todo-history-YYYY-MM-DD.md
python3 tools/board.py lost --base origin/main                   # before every push: exit 0
```

On a rebase or merge conflict in either file, do **not** edit the markers by
hand: `python3 tools/board.py resolve TODO.md` (and the same for
`docs/research/claims.md`) merges task blocks and claim rows by ID from the
three index stages, keeps both sides' additions, and leaves only a unit both
sides changed in conflict markers (exit 1). Then `git add` and run
`todo_check.py`/`claims_check.py`. Prose sections (rules, Priorities) may still
be edited normally; `--dry-run` prints the diff of any command.

## Worktrees (worktrunk)

Parallel agents never share a checkout. Every task runs in its own git
worktree on its own branch, managed with [worktrunk](https://worktrunk.dev)
(`wt`, install: `cargo install worktrunk` or `brew install worktrunk`).
Commands below are from the worktrunk docs (v0.82); `wt <cmd> --help` is
authoritative if they drift.

- **One task = one worktree = one branch = one draft PR.** The primary
  checkout stays on `main`: nobody commits there, and it is the source the
  `pre-start` hook links `archive/` from. Never `git checkout` another branch
  inside someone else's worktree.
- **Pair mode:** the driver creates the worktree; the navigator works in the
  *same* worktree read-only (git refuses one branch in two worktrees). The
  navigator may run checks there but never commits, edits or writes golden
  files.
- **Create** (after `git fetch`; base on `origin/main`, because a bare
  `--create` branches from the local `main`, which may be stale):

  ```bash
  git fetch origin
  B=task/m9.35-sec1-load-model            # task/<id-lowercase>-<slug>
  wt switch --create "$B" --base origin/main --no-cd --yes
  cd "$(git worktree list --porcelain | awk -v b="refs/heads/$B" \
        '/^worktree /{p=substr($0,10)} $0=="branch "b{print p}')"
  ```

  `--no-cd`: an agent's shell has no `wt` shell integration, so `cd` to the
  path yourself (above) and use absolute paths. `--yes` approves the
  project hook in `.config/wt.toml` without a prompt. The branch has no
  upstream yet; the claim push (`git push -u origin "$B"`, rule 2 above)
  sets it. Make the claim commit and push it **immediately** after
  `wt switch --create`, before anything else in the worktree: until it is
  pushed with a draft PR, nobody can see the task is taken. The default path is `../OSM2Leaf.<branch-sanitized>`, outside the
  repo.
- **`archive/` in the worktree:** the `pre-start` hook symlinks every file
  of the primary checkout's `archive/` into the new worktree, so `gate.py`
  and `selftest.py` see `head256.img` and do not SKIP. Check with
  `ls -l archive/` before you quote a gate result. Without `wt`, use
  `git worktree add -b "$B" ../OSM2Leaf."${B//\//-}" origin/main` and
  create the same links by hand.
- **Find work in progress:** `wt list` (branches, worktrees, ahead/behind,
  dirty state). It does not replace the claim: the draft PR `[ID]` and the
  `Owner:` line are still the only claim other agents see.
- **Remove only after merge.** When the task's commits are on `origin/main`
  and the PR is merged: `wt remove "$B"` from the primary checkout (deletes
  the worktree and the local branch once it is integrated). Removing a
  worktree before the push and merge has cost work (TL log 2026-11-09).
  An abandoned claim (ghost claim, see prompt_tl.txt): close the PR,
  then `wt remove -D "$B"`. `wt step prune --dry-run` lists merged
  worktrees older than a day; `wt step prune` removes them (it skips dirty
  ones).
- **Do not use `wt merge`, `wt step push` or `wt step commit`.** Merges go
  through the PR after `gh pr checks` (TL prompt); commits follow
  "Commit style" below.
- **Claude Code subagents** with `isolation: "worktree"` create detached
  trees under `.claude/worktrees/` (30+ stale ones were found, SM log
  2026-11-13). Prefer an explicit `wt switch --create` per task. If you use
  `isolation`, install the worktrunk plugin first (`wt config plugins claude
  install`), which routes it through `wt switch --create` / `wt remove`;
  it branches from the local default branch, so fast-forward the primary
  `main` (`git pull --ff-only`) before spawning.

## Before you search firmware code

Four facts cost this project whole sessions:

- **SH-4 code is little-endian.** A big-endian search finds nothing *and looks
  like a refutation* (M8.E1 vs M8.E1b). `tools/sh4dis.py` pins the convention.
- **All executable sections are readable.** Build A has **zero compressed
  executable sections** (149 code sections, 22.8 MB); the 245 compressed
  sections (30.2 MB) are `.data` and resources (C-2128). So "searched every
  section and did not find it" is a *complete* search — the failure is the
  **signature**, not hidden bytes. (The "56 % compressed" reading counts all
  sections; do not use it to excuse a search.)
- **Derive the signature; do not guess it from the doc.** The `POINT` walker
  was missed twice by searching the byte grammar in `refer.md`; it reads a
  packed `u16` (`0x3ff`/`0xfc00` masks) and was found by *executing* the code
  (C-2129, `tools/point_walk_l3.py`). Prefer an L3 run or the writer's inverse.
- **"No static caller" usually means an indirect call**: the pointer lives in
  `.data` and the call is `jsr @Rn` with `Rn` loaded from a table.

- **"Compressed `.data`" is mostly zeros and import slots (H49, C-3440).**
  Of the 30.2 MB in compressed sections of build A only **1.67 MB (5.5 %)**
  are stored bytes (`cerom.py comphdr --all`, `uncompressed_len`); the rest is
  BSS, zero at load and written by the program. `Navi.exe` sec1 is 16.7 MB
  with **98,330 B** initialised, and its first 0xd38 B are the **import
  address table** (846 slots), which the loader overwrites. Before you write
  "blocked: in compressed sec1", run
  `python3 tools/va_class.py IMG --module M --resolve-with 0x3e00200 VA`:
  `IAT` → bind the import to a stub (M9.35); `BSS` → find the code that writes
  it (decompressing yields zeros there); only `INIT` waits for M1.2f.

Compressed `.data` that is really `INIT` stays unreadable until M1.2f/M8.E1 —
that blocks M1.3/M1.4 and some constant tables, **not** reader searches and
not runs that touch IAT/BSS addresses. Verified decompressor entries
(LE): `DECOMP_WRAP 0x88037590`, `DECOMP_SECT 0x88037464`,
`DECOMP_BLK 0x8803a384` (loader flag test `0x88038666` in `fn 0x880385e4`).

## Commands

Vendor images are **not** required for most work, and "no image on this
machine" is never a blocker (rule 11): `https://files.viaaq.eu/sd-images/`
serves the EU 2011, US 2011 and 2014/2016 images (7.4–7.5 GB each; `curl -r
0-268435455` gets the 256 MiB firmware head in about a minute).

```bash
python3 tools/gate.py                     # the standing gate: one PASS/FAIL/SKIP policy
python3 tools/selftest.py                 # all tools that have --selftest
python3 tools/selftest.py --only imgpatch # one tool
python3 tools/claims_check.py             # ledger: duplicates, unregistered claims
python3 tools/realcheck.py IMG256         # pinned checks on real bytes (exit 2 = no image)
python3 tools/l3check.py --build-corpus   # L3 rung; exit 3 = nothing runnable, never a pass
```

`tools/gate.py` is the standing gate the TL/QA roles run: it runs
`selftest.py`, `claims_check.py --strict --count-check`, `todo_check.py` and
`fn_audit.py --corpus … --overlay …` in one fixed order and prints one
`PASS/FAIL/SKIP (reason)` table (plus `--json`). **A SKIP is never a pass**: it
exits 0 only when every *runnable* gate passed, and a missing
`archive/head256.img` makes `fn_audit` a named `SKIP`, not a silent
`passed=` line. Use `--board-clean` to add `todo_check --strict` (red until
H53), and `--json -` for a stdout document. CI runs it on every PR.

Verification ladder for a data/code change, in order:

```bash
python3 tools/cmpind.py verify REFER001     # expect 194/194 OK
python3 tools/cardcheck.py --root <root>    # L1 structural
python3 tools/l2check.py --root <root>      # L2 round-trip + golden
cd tools/ze0-viewer && python3 harness.py verify <tile>   # byte-identical tiles
```

- `l2check.py --cmp-limit 20 --no-tiles` for a fast pass; `--update-golden`
  only after an intentional decoder change, never to make a failure pass.
- Recompression needs **stock zlib 1.3.1** (`python3.13`). zlib-ng (often
  Python 3.14) reproduces none of the factory streams; `tools/zlibinfo.py`
  reports the runtime and exits 3 when a byte-identical claim is unverifiable.
- Firmware image starts: A (apps, `Navi.exe`) `0x200200`, B (kernel/updaters)
  `0x3e00200`, C (kernel/test mode) `0x5200200`.

## Repo shape

- `tools/` — Python 3.10+, standard library only, entrypoints run directly.
  `tools/selftest.py` auto-discovers `--selftest`; new tools must have one.
- `tools/ze0-viewer/` — viewer plus a **checked-in** copy of the pinned
  `osm2clarion` tools in `tools_ze0/`; `setup.sh` only audits/regenerates it
  against a git-ignored `vendor/` clone (see `docs/format/ze0-tools.md`).
- `docs/format/` living format knowledge · `docs/experiments/` append-only
  records (`TEMPLATE.md` carries the required five-part Method) ·
  `docs/research/` claims, roadmap, protocols · `profiles/` build profiles.
- `archive/` — git-ignored vendor data. Working data lives outside the repo;
  on this machine the full EU 2011 image is
  `/home/marek/projekty/leafre-work/leaf2011.img` (SHA-256 `105e2032…76307`),
  extracted tree `leafre-work/root/`.
- **Scratch goes in the home tree, not `/tmp`.** `/tmp` here is a 3.8 GiB
  tmpfs (RAM) and has filled twice in one day: `mkcard --selftest` died with
  `ENOSPC` and a 7.5 GB extraction could not be written. Use
  `~/projekty/leafre-work/scratch/<task>/` for intermediates, generated
  trees and probe work dirs (`run.sh --workdir`, `ce_qemu_probe.py
  --workdir`, `build.sh --srcdir`), and delete the directory when the task's
  EXP is written. `/tmp` is fine only for a few-MB file that the same
  command removes. Anything big enough to make you think twice about the
  disk belongs in the home tree; a scratch directory left behind is a task
  that is not finished.

## Format facts agents get wrong

- Common header text is UTF-16 **big-endian**, only `0x000`–`0x17f`; `0x180`
  onward is binary.
- `REFER001/*.cmp` is **not** one zlib stream: `chunk_count` independent
  streams indexed by `.ind`.
- `.ind` = `u32 uncompressed, u32 compressed, u32 count, u32 chunk_size
  (0x10000), u32 offsets[count]`. Payloads keep the 512-byte header.
- `REFER002` has **16 files**, not 194; it is a separate EV/charging layer.
- `DRSTR001.DAT` has **no header**: root `/` at `0x0000`, 40-byte nodes, then
  32-byte entries. Entry `value` = logical size for `.cmp`, on-disk size for
  `MAPAL001` tiles, recursive total for directories. Entry case is preserved
  (US stores `ltntbl.dat`).
- `MAPAL001` has 45 `BxxRyyR.DAT` + `LEV3456R.DAT`; B/R are hex:
  `lat_min = int(B,16)*2/3`, `lon_max = 108-int(R,16)`, 5.333° × 8°. Stream
  keys `A = 32768 + lat*192`, `B = 52736 + lon*128`, plus a table tag.
- `COORD001` is a 33-entry region-bbox table at `0x1010`:
  `lat = (x-32768)/192`, `lon = (y-52742)/128`. The same formula covers
  `ADDRE`/`POINT` ids; `ADDRE`/`POINT` share ids (join is street + house no.).
- Tile **section 4 is an administrative/place-name index**, not geometry. Road
  names come from the odd partner record's names section.
- `REFER001/INDEX003.DAT` does **not exist** on EU/US 2011 cards; the firmware
  string exists but the path is conditional (M3.12).
- The `0..2047` coordinate bound is a runtime/bit-packed constraint, not a
  plain-u16 storage rule; raw payloads contain larger `u16` values.
- Prefer `tools/mesh_grid.py`, `tools/cmpind.py`, `tools/cmpind_writer.py`,
  `tools/coord.py` over re-deriving any of the above.

## Writing data back

- **Unchanged file:** preserve original streams (or copy the pair) —
  byte-identical on any machine.
- **Changed file:** recompress only 64 KiB chunks containing changed bytes,
  keep the rest verbatim, rebuild `.ind` offsets.
- **New/whole-file rewrite:** stock zlib 1.3.1, level 6, wbits 15, memLevel 8,
  default strategy.
- **One-variable test cards:** `tools/imgpatch.py` writes a file into its
  existing cluster chain (FAT layout, timestamps, root label untouched);
  `tools/mkcard.py` rebuilds the whole partition for generated trees.

## Firmware: use the CE ROM TOC, and do not redo these dead ends

Start every address with `tools/cerom.py` (never fitted deltas):

```bash
python3 tools/cerom.py --image-start 0x200200 IMG256 romhdr
# expect: nummods=149 numfiles=1 cpu=0x01a6 physfirst=0x8cae1000 physlast=0x8e233c88
```

`ROMHDR` sits at file `0x01951b78`; `tools/cerom.py` also does `sections`,
`va2file`, `file2va`, `extract`, `memmap`, `comphdr`, `imports`, `exports`,
`thunks`. `tools/sh4xref.py` answers "who loads this VA" and "what does this
function call" — use it instead of ad-hoc scanning.

Retired, with no re-run: the `0x6fab2c → 0x6faeb0 → 0x6fb05c` "map-code
check" (it is `BT_MGR.dll`, C-520); global VA / module-base / delta fitting;
"no XIP table" (C-380/381, retracted); "static is closed for the reader"
(EXP-29, wrong address model); `NaviStateCC` vtable hunting; `+0x02200000`
as a map-code delta. `docs/research/todo-history-*.md` keeps the details.

Map-code checks (M2.5, M2.15): 11 bytes of kernel target info
(`KernelIoControl 0x0101302C` `+0x60`) vs `HDD_INFO.TXT` line 1, and a
`MapDBVer` range check — **not** the `0x06000000` copy, and `HDD_CHK.ATT` is
read only by `MapUpdate.exe`, not by `Navi.exe` at boot.

## Method that this repo already paid for

- **Test the textbook structure before inventing a model.** CE ROMs, FAT, zlib
  and PE have public layouts; start from `ECEC`/`ROMHDR` with its documented
  field order. EXP-05…29 were ~20 rounds of fitted parameters that mostly
  retracted each other.
- **Addresses come from structure, not code literals.** `cerom.py` gives
  module/section/offset; literal scoring with prologue percentages never
  proves a base (and `V − S` matches are not injective here).
- **Prefer checks that can fail loudly** — a wrong hypothesis should give 0 %,
  not 40 %. "The name resolves", "physfirst equals the image base", "an
  independent anchor reproduces" are tests that can fail.
- **One module, one claim.** Attribute every VA through `cerom.py` and say so
  in the claim row.
- **Cheap before expensive.** The firmware is in the first ~100 MB, so use
  ranged reads, cross-year diffs and the offline validators before asking for
  hardware, a spare card or a full download.

## Evidence and retraction

- New experiment: copy `docs/experiments/TEMPLATE.md`, name
  `EXP-YYYY-MM-DD-<TASK>-slug.md`. Record sample SHA-256, runnable commands,
  controls (positive and negative), the counted corpus, and the falsifier —
  then observations, then interpretation. Never mix the two.
- A claim is never deleted: mark `RETRACTED` (keep the ID) and add a new claim
  with `Supersedes: C-xxx`.
- External links → `docs/research/sources.md`; unknowns →
  `docs/research/open-questions.md`; loose threads → `TODO.md`.
- Negative results are first-class; a negative without a positive control is
  not a result.
- Rule 13: a generated format is *confirmed* only when its firmware reader has
  a VA in `docs/format/`, and *accepted* only when an L3 run (firmware fragment
  harness) or L4 run (full-system emulator, M8) reads our file. L5 (car/bench)
  remains the final acceptance oracle when hardware is available. Level mapping
  (2026-11-09): before 2026-11-09 L4=car/bench, L5=full-system emulator; after
  2026-11-09 L4=full-system emulator, L5=car/bench. See `feedback-loop.md`.

## Data, license, safety

- Never commit vendor data: images, dumps, firmware, `.DAT`, `.cmp`, `.ind`,
  `.AGM`, `.TTS`, `.GID`. `.gitignore` also drops `*.img`/`*.7z`. Keep them in
  `archive/` or outside the repo; `git add -f` only for tiny synthetic
  fixtures.
- One exception, decided by the repository owner (2026-11-22, M8.C1k):
  `firmware/unit-flash/nk1-QY7200ND.bin`, the unit-flash kernel image NK1,
  so that `-M ze0` runs without a unit dump. Its README says what was cut
  out and checked. No other part of a unit dump (rest of the NAND, `SRAM`,
  `VFlash`, `PROD`) and no card image is committed.
- Code is GPL-3.0-or-later; OSM-derived data is ODbL-1.0. Link to
  incompatible projects instead of copying code.
- The original SD card is read-only: back up, verify the hash, test on a
  spare card.
- Commit only offsets, counts, hashes and short header bytes from vendor data.

## Commit style

Small, logical commits. Imperative subject ≤ ~72 chars, no trailing period;
prefixes `docs:`, `tools:`, `format:`, `fix:`, `chore:`. Explain *why* in the
body.
