# Dev assignments — TL batch 7, 2026-11-23

Read `AGENTS.md`, `prompt_common.txt`, the "How to take a task" rules at the
top of `TODO.md` (rules 1–17), and this file first. Work **only** in your
worktree. Nobody merges; the TL merges.

## Every task, first steps (before planning or coding)

1. In your worktree, re-read your task block on `origin/main`
   (`git show origin/main:TODO.md`) and the open PR list
   (`gh pr list --state open`) — if another PR claims your ID, stop and tell
   the TL.
2. `python3 tools/board.py claim <ID> --owner <branch>` (changes only your
   task line); commit `todo: start <ID>`; `git push -u origin <branch>` at
   once, before any other work.
3. Open a **draft PR** `[ID] short title` with `gh pr create --draft`.
4. Check `archive/` shows image symlinks; if not, tell the TL.

## Rules that bite in this batch

- Only `files.viaaq.eu` and package registries are reachable from the Claude
  sandbox; GitHub git operations work; OSM hosts do not. This host has normal
  internet, but do not commit OSM extracts.
- SH-4 code is **little-endian**. Start every firmware address with
  `tools/cerom.py`; use `tools/sh4dis.py`, `tools/sh4xref.py`,
  `tools/nk_decomp.py pdata`. Never fitted deltas or ad-hoc scans. Derive
  signatures from L3/writer inverse, not from prose.
- Edit `TODO.md` and `docs/research/claims.md` **only** through
  `python3 tools/board.py` (`claim`, `done`, `block`, `field`, `add-claims`,
  `resolve` on conflict). `board.py lost --base origin/main` must exit 0
  before every push.
- Scratch (cards, trees, QEMU dirs, logs) goes in
  `~/projekty/leafre-work/scratch/<ID>/`, never `/tmp`; delete it when the
  EXP is written.
- No vendor bytes in the repo (offsets, counts, hashes, short header bytes
  only). `git add -f` only for tiny synthetic fixtures.
- Finish: `Status: done` only if your own `Done when` passes — run the exact
  commands; otherwise `Status: blocked` + one-line `Blocker:` + `Unblock:` +
  negative EXP. Last commit: work + `python3 tools/board.py done <ID>
  --result "…"`. Run `python3 tools/selftest.py`, `tools/claims_check.py`,
  `tools/todo_check.py`, paste results into the PR body, then `gh pr ready`.
- New experiment: copy `docs/experiments/TEMPLATE.md` to
  `EXP-2026-11-23-<ID>-<slug>.md`; observations separate from interpretation;
  positive and negative controls; every number quoted from a command.
- Do not merge — the TL merges.

## Pair protocol (both agents get this file)

- **Driver** writes code, commits, writes the EXP, makes the claim commit and
  the PR. **Navigator** writes no code: reviews, runs checks, holds the
  evidence bar from AGENTS.md. The navigator writes the EXP Method section
  (positive/negative controls, falsifier, expected result) before the build;
  the driver inserts it in the EXP.
- Rounds: (1) driver sends a short plan (approach, signature/format source,
  files, intended `Done when`) to the TL, who relays to the navigator;
  navigator approves or returns it (endianness, derived vs guessed signature,
  indirect calls, retired leads). (2) navigator writes the EXP Method.
  (3) driver builds in small commits, one-line note per commit. (4) navigator
  reads the diff, re-runs `Done when` + controls, answers APPROVE or CHANGES
  (max 3 rounds).
- Before APPROVE the navigator must (a) for any gate/snapshot/artifact a later
  task reads, mutate it negatively and show the gate fails; when a diff widens
  a skip/ignore set, plant a real citation inside the set and show the gate
  still reports it; (b) check that every number in the EXP/claims is quoted
  from a command's output, never typed.
- The EXP has a `Corrections after navigator review` section (or the heading
  removed if there were none).

## Assignments

Each line: `ID | branch | worktree | mode`.

- M9.72 | task/m9.72-us-locmap-walk | /home/marek/projekty/OSM2Leaf.task-m9.72-us-locmap-walk | pair
- M5.69 | task/m5.69-even-odd-splice | /home/marek/projekty/OSM2Leaf.task-m5.69-even-odd-splice | pair
- M4.96 | task/m4.96-tile-unexplained-grades | /home/marek/projekty/OSM2Leaf.task-m4.96-tile-unexplained-grades | pair
- M9.12 | task/m9.12-card-gate | /home/marek/projekty/OSM2Leaf.task-m9.12-card-gate | pair
- M9.71 | task/m9.71-exp-check | /home/marek/projekty/OSM2Leaf.task-m9.71-exp-check | pair
- M8.H76 | task/m8.h76-hashutil | /home/marek/projekty/OSM2Leaf.task-m8.h76-hashutil | solo (pure housekeeping, byte-identical refactor; task says Pair: solo)

Skipped this batch, with the reason: every M6/L5 task (no hardware); M8.H64,
M8.H12, M5.83, M5.92 (QEMU boot / L4 resource, shared 8 CPUs under parallel
agents); M5.61 (blocked, its unblocks are this batch's M5.69); M4.97 (blocked
on M4.55/M9.65, an open draft); M5.73/M4.66 (lower value, file overlap with
the H task); M5.81 (needs a US card tree not extracted here); IDs in open PR
titles (M5.100, M5.82, H132, M4.85, M9.62, M9.64, M9.65).
