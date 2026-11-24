# Dev assignments — TL batch 8, 2026-11-23

Read `AGENTS.md`, `prompt_common.txt`, the "How to take a task" rules at the
top of `TODO.md` (rules 1–17), and this file first. Work **only** in the
worktree named in your prompt. Nobody merges; the TL merges.

## Every task, first steps (before planning or coding)

1. In your worktree, re-read your task block on `origin/main`
   (`git show origin/main:TODO.md | grep -A45 '<ID> —'`) and the open PR list
   (`gh pr list --state open`). If another PR claims your ID, stop and tell the TL.
2. Immediately: `python3 tools/board.py claim <ID> --owner <branch>` (changes
   only your task line); commit `todo: start <ID>`; `git push -u origin <branch>`
   before any other work. Open a **draft PR** `[ID] short title` right after.
3. Verify `ls archive/` shows the image symlinks; if not, tell the TL.
4. Produce the requested short plan and STOP. Do not implement until the TL
   relays navigator approval.

## Rules that bite in this batch

- SH-4 code is **little-endian**. Start every firmware address with
  `tools/cerom.py`/`tools/sh4xref.py`/`tools/sh4dis.py`; derive signatures from
  structure or an L3 run, never guess from prose. Do not redo the retired
  leads listed in AGENTS.md.
- Edit `TODO.md` and `docs/research/claims.md` **only** with `tools/board.py`
  (`claim`, `done`, `block`, `field`, `add-claims`, `resolve`). Run
  `python3 tools/board.py lost --base origin/main` before every push (must print
  0 lost). On a conflict, `python3 tools/board.py resolve <file>`, `git add`,
  continue the rebase — never hand-edit markers or paste a whole file.
- Scratch (cards, trees, QEMU dirs, probe outputs, logs) goes in
  `~/projekty/leafre-work/scratch/<ID>/`, never `/tmp` (3.8 GiB tmpfs, quota
  exceeded twice). Short TMPDIR paths only (<= ~50 chars) for tools that use
  Unix sockets. Delete your scratch dir when the EXP is written.
- No vendor bytes in the repo (offsets, counts, hashes and short header bytes
  only). `git add -f` only for tiny synthetic fixtures.
- New tools need a `--selftest` discovered by `tools/selftest.py`.
- Numbers in the EXP/claims must be quoted from a command that prints them;
  never typed by hand. Separate observations from interpretation.
- Finish: `Status: done` only if your own `Done when` passes; otherwise
  `blocked` with a one-line `Blocker:`, an `Unblock:` and a negative EXP.
  Last commit: work + `python3 tools/board.py done <ID> --result "…"` (or
  `block`). Run `python3 tools/selftest.py`, `tools/claims_check.py`,
  `tools/todo_check.py` and `python3 tools/gate.py` before reporting done.
- Do not merge, do not rebase onto `main` unless the TL asks.

## Resources on this host

- Firmware heads: `archive/head256.img` (EU2011 A), `archive/us256.img`,
  `archive/eu2014-256.img`, `archive/eu2016-256.img`.
- Full EU 2011 tree: `/home/marek/projekty/leafre-work/root`; factory tree:
  `/home/marek/projekty/leafre-work/m5.4/card-factory`; full EU card image:
  `/home/marek/projekty/leafre-work/leaf2011.img` (7.5 GB).
- OSM extracts: `/home/marek/projekty/leafre-work/osm/` (dolnoslaskie-latest.osm.pbf
  174 MB, poland-latest if present, 2.6 GB total). Do not commit extracts.
- QEMU: `/home/marek/projekty/leafre-work/qemu-ze0-m8h6/qemu-system-sh4`.
- KIWI sources: `docs/research/kiwi-sources.md` (link/field names only, never
  copy GPL code into this repo).

## Task briefs (mode)

| ID | Branch | Mode | Files you own |
| --- | --- | --- | --- |
| M9.18 | task/m9.18-lev3456-l3-targets | pair | L3 harness/targets, your EXP/claims. **Do not edit `docs/research/reader-coverage.md`** (M8.H64 owns it). |
| M8.H64 | task/m8.h64-p0-card-l4 | pair (required) | `docs/research/reader-coverage.md` (F4 column), your EXP/claims. |
| M4.95 | task/m4.95-ref-shield-writer | pair (required) | name writer in `tools/tilewriter.py`/`tools/section4_places.py`/viewer `fa_encode.py`, `docs/research/osm-pipeline.md`, your EXP/claims. |
| M4.94 | task/m4.94-kiwi-probes-tree | pair (required) | `tools/kiwi_probe.py`, `tools/kiwi_bg_probe.py`, `tools/kiwi_road_probe.py`, `tools/kiwi_route_concepts.py`, M4.67/68/69/70/72 EXP `## Reproduction` lines, your EXP/claims. |
| M4.66 | task/m4.66-kiwi-types | solo (`Pair: solo`) | new `tools/kiwi_types.py`, `docs/format/{map-tiles,cmp-ind,drstr}.md`, your EXP/claims. |
| M5.77 | task/m5.77-dolnoslaskie-numbers | solo (`Pair: solo`) | `tools/osm_ingest.py`, `tools/mesh_split.py`, `tools/slot_budget.py`, your EXP/claims. |
| M4.8b | task/m4.8b-coord-poi-check | pair | `tools/coord.py`, your EXP/claims. |
| M8.H68 | task/m8.h68-ze0-ps | solo (`Pair: solo`) | new `tools/ze0_ps.py`, your EXP/claims. |
| H28 | task/h28-l3-in-ci | pair | `.github/workflows/ci.yml`, CI docs, your EXP/claims. |
| M4.73 | task/m4.73-kiwi-guidance | solo (`Pair: solo`) | `tools/inter_table.py`, `docs/format/refer.md`, `docs/research/kiwi-sources.md`, your EXP/claims. |

Conflict-avoidance: stay inside your own files. Two tasks writing the same
tool or format doc do not run in the same batch. If you need a change outside
your file list, stop and ask the TL.
