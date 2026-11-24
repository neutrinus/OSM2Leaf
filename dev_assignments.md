# Dev assignments — TL batch, 2026-11-23

Read `AGENTS.md`, `prompt_common.txt` and the rules in `TODO.md` first.
Your worktree, branch and task ID are below. Work **only** in your worktree.
Nobody merges; the TL merges.

## Every task, first steps (do this before planning or coding)

1. In your worktree: `python3 tools/board.py claim <ID> --owner <branch>`
   (changes only your task line), commit `todo: start <ID>`, `git push -u origin <branch>`.
2. Open a **draft PR** `[ID] short title` with `gh pr create --draft`.
3. Re-read your task block on `origin/main` (`git show origin/main:TODO.md`) and
   your PR count with `gh pr list --state open` — if another PR claims the same ID,
   stop and tell the TL.

## Rules that bite in this batch

- Only `files.viaaq.eu` (and package registries) are reachable from this sandbox;
  GitHub is reachable, `github.com` git operations work. OSM hosts do not.
- Vendor images are in `archive/` (symlinked into every worktree): `head256.img`
  (EU2011 build A), `us256.img`, `eu2014-256.img`, `eu2016-256.img`, full cards in
  `archive/sd-images/`. Firmware image starts: A `0x200200`, B `0x3e00200`, C `0x5200200`.
- SH-4 code is **little-endian**; use `tools/sh4dis.py`, `tools/cerom.py`,
  `tools/sh4xref.py` — never ad-hoc scans or fitted deltas.
- Edit `TODO.md` and `docs/research/claims.md` **only** through `tools/board.py`
  (`claim`, `done`, `block`, `add-claims`, `resolve` on a conflict).
  `python3 tools/board.py lost --base origin/main` must exit 0 before every push.
- Scratch (cards, trees, QEMU dirs, logs) in
  `~/projekty/leafre-work/scratch/<ID>/`, never `/tmp`; delete it when the EXP is written.
- No vendor bytes in the repo (offsets, counts, hashes, short header bytes only).
  `git add -f` only for tiny synthetic fixtures.
- Finish: `Status: done` only if your own `Done when` passes — run the exact
  commands; otherwise `Status: blocked` + one-line `Blocker:` + `Unblock:` + negative EXP.
  Last commit: work + `python3 tools/board.py done <ID> --result "EXP-…; …"`.
  Run `python3 tools/selftest.py`, `tools/claims_check.py`, `tools/todo_check.py`
  and paste the results into the PR body; then `gh pr ready`.
- New experiment: copy `docs/experiments/TEMPLATE.md` to
  `EXP-2026-11-23-<ID>-<slug>.md`; observations separate from interpretation;
  controls (positive and negative); every number quoted from a command.
- If your task is `Runner: non-Claude`: this host has normal internet except OSM
  hosts (rule 12) — record the URL, date and SHA-256 of anything you fetch.

## Pair protocol (both agents get this file)

- **Driver** writes code, commits, writes the EXP. **Navigator** writes no code
  in the worktree: reviews, runs checks, holds the evidence bar.
- Rounds: (1) driver sends a short plan, navigator approves or returns it
  (endianness, derived vs guessed signature, indirect calls, retired leads);
  (2) navigator writes the EXP Method (positive/negative controls, falsifier,
  expected result); (3) driver builds in small commits, one-line note each;
  (4) navigator reads the diff, re-runs `Done when` + controls, answers
  APPROVE or CHANGES (max 3 rounds).
- Before APPROVE the navigator must (a) for any gate/snapshot/artifact a later
  task reads, mutate it negatively and show the gate fails; when a diff widens
  a skip/ignore set, plant a real citation inside the set and show the gate
  still reports it; (b) check that every number in the EXP/claims is quoted
  from a command's output, never typed.
- The EXP has a `Corrections after navigator review` section (or the heading
  removed if there were none).

## Assignments

Each line: `ID | branch | worktree | mode | navigator target`.

- M1.49 | task/m1.49-ui-strings | /home/marek/projekty/OSM2Leaf.task-m1.49-ui-strings | pair
- M4.65 | task/m4.65-kiwi-sources | /home/marek/projekty/OSM2Leaf.task-m4.65-kiwi-sources | pair
- M5.71 | task/m5.71-verify-factory-parcels | /home/marek/projekty/OSM2Leaf.task-m5.71-verify-factory-parcels | pair
- M5.70 | task/m5.70-l2-even-slot | /home/marek/projekty/OSM2Leaf.task-m5.70-l2-even-slot | pair
- M5.68 | task/m5.68-stream-jsonl | /home/marek/projekty/OSM2Leaf.task-m5.68-stream-jsonl | pair
- M2.20 | task/m2.20-region-recoverable | /home/marek/projekty/OSM2Leaf.task-m2.20-region-recoverable | pair
- M8.H11 | task/m8.h11-l3-l4-parity | /home/marek/projekty/OSM2Leaf.task-m8.h11-l3-l4-parity | pair
- M9.67 | task/m9.67-locmap-host-model | /home/marek/projekty/OSM2Leaf.task-m9.67-locmap-host-model | pair

Skipped this batch, with the reason: M5.69 (remote branch deleted under the task's
old owner, no PR — rebase cost put after the fresh claims); every M6/L5 task
(no hardware); M8.H64, M2.22, M2.21, M8.H12 (each runs the full QEMU boot many
times, and the boot is ~220 s while QEMU rebuilding plus ten agents share 8 CPUs);
M9.16 (its note redirects to M9.60/M9.61, both done — needs a PO/board pass);
M4.2, M5.77/M5.78/M6.9 (the `Runner: non-Claude` OSM/hardware ones with no extract
for the needed cell); M4.8b/M4.28/M5.72/M9.62/M9.64/M9.65/M6.19 (claims held by
open branches or PRs).
