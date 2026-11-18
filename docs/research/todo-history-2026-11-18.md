# TODO history — 2026-11-18 (PO grooming archive, 16th pass)

Done tasks moved from `TODO.md` on 2026-11-18: `Status: done`, block named
by no live task (fixpoint over the whole live board: no open or blocked
block's text names the ID), and completed on `origin/main` more than 24 h ago
(tick/merge commit dates on `origin/main` are the authority; cutoff
2026-11-17T06:45Z). Earlier archives: `todo-history-2026-11-05.md`, `-06.md`,
`-09.md`, `-13.md`, `-15.md`, `-16.md`, `-17.md`.

The other 61 done blocks stay on the board: a live task still names each of
them. A moved block may still be named by *another done block's* fields
(e.g. H79/H80 are named by done H81's notes); that is merge provenance, not a
live dependency.

## H

- [x] **H79 — M1.31 evidence cites `/tmp/opencode/us256.img`; make the US head re-creatable and retarget Claim 26 at `US256`**
  - Status: done · Owner: task/h79-m131-us-head · Critical: no · Pair: solo
  - Depends: H62 (the `US256` fetch key; H62 is open, so the `head -c` line is the interim fix), H75 (the same defect already fixed for C-3703)
  - Goal: `EXP-2026-11-16-M1.31-leaf-census.md` names `/tmp/opencode/us256.img` in its sample and commands (6 times) and C-3962/C-3965 carry `--us /tmp/opencode/us256.img`; a reader on a fresh checkout cannot re-run them, which is the exact class H75 repaired for C-3703. The head is the same `70d945d8…`.
  - Precheck: `grep -c "/tmp/opencode/us256.img" docs/experiments/EXP-2026-11-16-M1.31-leaf-census.md docs/research/claims.md` prints `6` and `4`.
  - Scope: the M1.31 EXP (commands and the sample table) and the C-3962/C-3965 evidence cells only: replace `/tmp/opencode/us256.img` with `archive/us256.img`, and add the re-creatable line `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img > archive/us256.img` (hash `70d945d8…`) next to the first use, or cite H62's `fetch_image.py --image US256` once H62 lands. No new mechanism, no fixture edit.
  - Input: `docs/experiments/EXP-2026-11-16-M1.31-leaf-census.md`, `docs/research/claims.md` C-3962/C-3965, `docs/experiments/EXP-2026-11-16-H75-m1.27-evidence.md` (the pattern), `archive/sd-images/LEAF_2011-2012_US.img`.
  - Hints: `head -c 268435456 … | sha256sum` must print `70d945d8…04da`; if H62 has merged by the time this is taken, prefer `fetch_image.py --image US256` and delete the `head -c` line. Run the M1.31 census once on `archive/us256.img` after the edit so the numbers are re-quoted, not retyped.
  - Done when: `grep -c "/tmp/opencode/us256.img" docs/experiments/EXP-2026-11-16-M1.31-leaf-census.md docs/research/claims.md` prints `0` and `0`; the cited US HEAD command with `archive/us256.img` prints `70d945d8…` (or `fetch_image.py --image US256` verifies it); `python3 tools/claims_check.py` and `--strict` exit 0.
  - Stop: if `archive/sd-images/LEAF_2011-2012_US.img` is absent and H62 has not merged, cite only the pinned SHA-256 and the existing `/tmp` path as `HYPOTHESIS (not re-creatable here)` rather than inventing a path.
  - Result: EXP-2026-11-16-M1.31-leaf-census `Correction (H79)`; C-4020–C-4023. The US head is `archive/us256.img`, re-created by `head -c 268435456 archive/sd-images/LEAF_2011-2012_US.img > archive/us256.img` (`70d945d8…04da`, git-ignored). The M1.31 EXP's 6 and the ledger's 4 `/tmp/opencode/us256.img` mentions are 0; the same edit repairs C-3741/C-3742 (M1.28) and makes C-3742's flip step runnable. Every measured number is unchanged (census 598/77/2, `TRUNCATED … 0x4a16`, `13 rows, 0 mismatch`); `claims_check --strict` exit 0.
  - Claims: C-4020–C-4029

- [x] **H80 — H71's Precheck selects claim rows by a line range that no longer exists**
  - Status: done · Owner: task/h80-precheck-id · Critical: no · Pair: solo
  - Depends: H71 (the task whose Precheck this repairs)
  - Goal: H71's Precheck is `sed -n '2802,2807p' docs/research/claims.md | grep -nE '…|\.\.\.'`; today those lines are C-3790–C-3792 (the C-3860/61/64 rows moved to 2824–2828 when M1.26/H74 added rows above them), so the precheck matches nothing and a reader concludes the task is moot. H71's own Done-when was already repaired to select by claim ID; its Precheck was not.
  - Precheck (H80, before the fix): the old selector `sed -n '2802,2807p' docs/research/claims.md` held only C-3790–C-3795, so `… | grep -cE 'C-386[014]'` printed `0`; the three rows are now found by ID: `grep -nE '^\| C-386[014] \|' docs/research/claims.md | cut -d: -f1` prints `2824`, `2825`, `2828`.
  - Scope: the H71 block's `Precheck:` line only: replace the line-range `sed` with an ID selector, e.g. `grep -nE '^\| C-386[014] \|' docs/research/claims.md | grep -cE '…'` on those rows (0 after H71), and a one-line note that IDs (not line numbers) are the anchor. No claim, no tool, no other H71 field.
  - Input: TODO.md H71 block, `docs/research/claims.md` C-3860/C-3861/C-3864.
  - Hints: this is the same rot retro-9 records for H71's Done-when (`sed -n '2802,2807p'`); a Precheck is a command a later agent runs, so it has to survive row insertions. Select by ID, never by line.
  - Done when: H71's Precheck command, run as written, selects the C-3860/61/64 rows (prints their count) and matches 0 elided spans after H71; `python3 tools/todo_check.py` passes.
  - Stop: none — if `claims.md` changes again before this lands, update the selector, not the line numbers.
  - Result: EXP-2026-11-16-H80-precheck-id; C-4030–C-4032. H71's Precheck now selects C-3860/61/64 by claim ID (`grep -nE '^\| C-386[014] \|'` → `3` rows, `2824/2825/2828`) instead of the stale `sed -n '2802,2807p'` (now C-3790–C-3795, `0` matches). The elided-span condition prints `0` at H71's merge `caff825` and today, so no measurement changed; `todo_check` OK, `--strict` 69.
  - Claims: C-4030–C-4039
