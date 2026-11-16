# EXP-20261116-H69: frozen `fn_audit` snapshot refresh and moved-only gate policy

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `archive/head256.img` SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (symlinked into the worktree from the repo's `archive/`, never copied)
- **Tools:** python3 3.13.1 (stdlib only); repo tools `tools/fn_audit.py`,
  `tools/selftest.py`, `tools/claims_check.py`, `tools/todo_check.py`
- **Claims:** C-3900–C-3909
- **Supersedes:** none (extends EXP-2026-11-16-M1.30-fn-audit-snapshot; its
  C-3861 SHA-256 for the old file stays a record of that file)
- **Superseded by:** none

## Question

Can the committed frozen `fn_audit` corpus (313 citations / 112 unique VAs)
be refreshed on current `main` so a fresh `--write-snapshot` reproduces it
byte-for-byte and `--corpus` exits 0, while a **moved-only** staleness (same
`(file,va,kind,class)` identity, only `line` changed) warns and exits 0
without ever weakening the `new`/`gone`/verdict-change failure?

## Hypothesis

`moved`-only drift is prose: the protected identity set is
`(file,va,kind,class)`, and `compare_live` already separates `moved` from
`changed`. If `audit_corpus` treats a moved-only diff as a warning (exit 0)
and keeps new/gone/verdict-change as exit 1, then the committed snapshot can
be refreshed from the current tree and stay a meaningful gate. **Falsifier:**
any fixture where a moved-only diff exits 1, or a new/gone/verdict-change
diff exits 0, refutes the split; a fresh `--write-snapshot` that does not
reproduce the committed file byte-for-byte refutes the refresh.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (build A `Navi.exe` head) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Old snapshot | `docs/research/fn-audit-corpus-2026-11-16.json`, SHA-256 `4606aa2aff292d72ec9651cfff0660c246bf1d23255fc59cab3348ea0878fe38`, 313 rows |
| Refreshed snapshot | same path, SHA-256 `2db48be11b5088571e2dea345caef535265716fcb1333fd017ac62ecce8eb17d`, 313 rows |
| Tool / version | python3 3.13.1, standard library only |
| Repo tool | `tools/fn_audit.py` (the only tool that produced the numbers) |

## Method

### 1. Sample and hash

The image is the 256 MiB build-A firmware head SHA-256 `92aa525d…` above;
the snapshot names the same hash in its `image_sha256` field, and `--corpus`
refuses an image whose hash differs (exit 2). The snapshot stores only
`file/line/va/kind/class/true_start` rows, the summary and the image hash —
no image bytes.

### 2. Commands

```bash
# Policy: moved-only drift warns + exits 0, new/gone/verdict-change exits 1.
python3 tools/fn_audit.py --selftest

# Reproduce the stale state on current main (old snapshot) -- policy makes
# this exit 0 with a CORPUS DRIFT warning instead of exiting 1.
python3 tools/fn_audit.py archive/head256.img \
    --corpus /tmp/opencode/h69-old-snapshot.json --quiet; echo $?

# Refresh deliberately, then prove the file is reproducible.
python3 tools/fn_audit.py archive/head256.img --scope docs \
    --write-snapshot /tmp/opencode/h69-fresh.json --quiet
cp /tmp/opencode/h69-fresh.json docs/research/fn-audit-corpus-2026-11-16.json
python3 tools/fn_audit.py archive/head256.img --scope docs \
    --write-snapshot /tmp/opencode/h69-fresh2.json --quiet
cmp docs/research/fn-audit-corpus-2026-11-16.json /tmp/opencode/h69-fresh2.json
sha256sum docs/research/fn-audit-corpus-2026-11-16.json
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet; echo $?

# Re-classification still fails independently of the live check.
python3 tools/fn_audit.py archive/head256.img \
    --corpus /tmp/opencode/h69-classflip.json --quiet --no-live-check; echo $?

python3 tools/selftest.py --only fn_audit
```

`/tmp/opencode/h69-old-snapshot.json` is the pre-refresh committed file
(`4606aa2a…`). `/tmp/opencode/h69-classflip.json` is the refreshed snapshot
with one `START` row relabelled `INSIDE`, its `class_sha256` re-signed and
the summary adjusted so only the image can tell.

### 3. Controls

- **Positive control:** a fresh `--write-snapshot` on the current tree
  produces a file byte-identical to the committed one (`cmp` silent) and
  `--corpus` on it exits 0 with the unchanged summary.
- **Positive control (policy):** the old snapshot run live is a pure
  `moved` diff (`0 new / 0 gone / 122 moved`) and exits 0 with the warning.
- **Negative controls (new `--selftest` fixtures, injected rows):**
  - `moved`-only → exit 0 + `CORPUS DRIFT` + `line-only drift` warning;
  - one `new` row → exit 1 (`CORPUS STALE: 1 new`);
  - one `gone` row → exit 1 (`CORPUS STALE: 0 new / 1 gone`);
  - verdict change at an unchanged key → exit 1 (`verdict change`);
  - verdict change that travels with a line move → exit 1 (`0 moved`,
    `verdict change`) — a move never masks a change;
  - the retained mixed case (1 new/1 gone/1 moved) → exit 1.
- **Negative control (real file):** `/tmp/opencode/h69-classflip.json`
  (relabelled class, re-signed fingerprint, adjusted summary) exits 1 on
  re-classification with `--no-live-check`, so the refresh did not turn the
  corpus into a file that trusts its stored class.

### 4. Scope

The `--scope docs` corpus (`TODO.md`, 13 `docs/format/*.md`,
`tools/l3_harness/targets.json`, `tools/chunk_decoder_l3.py`,
`tools/point_walk_l3.py`): 17 files, 313 citations, 112 unique VAs. Excluded:
`--scope l3` (M1.26), citations in `docs/research/*.md` and
`tools/README.md` (outside the glob, edited by hand), CI auto-refresh (none
added), and any row deletion (none; 313 rows before and after).

### 5. Falsifier

A moved-only fixture exiting 1, a new/gone/verdict-change fixture exiting 0,
a fresh write that differs from the committed file, or a `--corpus` run on
the refreshed file that exits non-zero would each refute the claim. All were
tested and none occurred.

## Observations

Refreshed snapshot diff vs the old committed file (`4606aa2a…`):

```
identity keys (file,va,kind):            168 old / 168 new, set equal
identity keys whose line changed:        44 (all TODO.md)
snapshot rows whose line changed:        188
class / true_start changes:              0
summary: 17 files, 313 citations, 112 unique VAs,
         START 229, INSIDE 0, CORRECTED 23, GAP 29 (leaf 29),
         AMBIGUOUS 0, UNMAPPED 32   (unchanged)
sha256 old 4606aa2aff292d72ec9651cfff0660c246bf1d23255fc59cab3348ea0878fe38
sha256 new 2db48be11b5088571e2dea345caef535265716fcb1333fd017ac62ecce8eb17d
```

Commands and exit codes:

```
fn_audit.py --selftest                          -> OK (49 checks, 0 failed)
old snapshot --corpus --quiet                   -> CORPUS DRIFT: 0 new / 0 gone / 122 moved, exit 0
--write-snapshot (fresh)                        -> exit 0, 313 citations / 112 unique VAs
cmp committed vs second write                   -> byte-identical
--corpus refreshed snapshot --quiet             -> exit 0
--corpus classflip --quiet --no-live-check      -> exit 1
selftest.py --only fn_audit                     -> PASS (0.06 s)
```

The 122 moved citation rows reduce to 44 distinct `(file,va,kind)` identities,
all in `TODO.md`; `docs/format/*.md`, `targets.json` and the two `*_l3.py`
files did not move. No identity was added, removed or reclassified.

## Interpretation

- **FACT:** on current `main` the old snapshot is moved-only stale (44
  identities / 122 citation rows / 188 row instances, all `TODO.md`) and a
  fresh write reproduces the refreshed file byte-for-byte
  (`2db48be1…`), 313 rows / 112 VAs, summary unchanged.
- **FACT:** with the policy, a moved-only live diff prints `CORPUS DRIFT` and
  exits 0; `new`, `gone`, a verdict change at an unchanged key, and a verdict
  change on a moved row each exit 1 (five selftest fixtures plus the retained
  mixed case).
- **FACT:** re-classification is independent of the live check — a relabelled
  row with a re-signed fingerprint still exits 1 under `--no-live-check`.
- **OBSERVED:** the earlier board note counted 97 moved rows on `626ccc2`; on
  this tree the same measurement is 122 moved citations (188 row instances,
  44 identities), i.e. more prose moved after that note — all line-only, none
  of it a citation-set change.
- **HYPOTHESIS:** none needed; this is a policy + refresh result, not a
  firmware or format claim.
- **UNKNOWN:** how often M1.26's standing gate will see moved-only drift in
  practice; the policy makes it a warning either way.

## Conclusion

`tools/fn_audit.py` now splits live drift into `CORPUS DRIFT` (moved-only:
warn, exit 0) and `CORPUS STALE` (new/gone/verdict change, including a change
that travels with a move: exit 1); `compare_live` reports a moved+unclassified
row as a verdict change rather than a benign move. The committed snapshot was
refreshed deliberately to `2db48be11b5088571e2dea345caef535265716fcb1333fd017ac62ecce8eb17d`
(313 rows / 112 VAs, summary unchanged, old hash
`4606aa2aff292d72ec9651cfff0660c246bf1d23255fc59cab3348ea0878fe38`) and a
fresh `--write-snapshot` reproduces it byte-for-byte. `tools/README.md`
documents the refresh procedure (only an intentional write; the diff is the
review artifact; no CI auto-refresh, no row deletion, stable `file:line:va`
sort). The `new`/`gone`/verdict-change failure was never weakened. Claims
C-3900–C-3909 register these commands.

## Follow-ups

- M1.26 consumes this policy for `--scope l3`; it must name `CORPUS DRIFT`
  (moved-only, exit 0) and `CORPUS STALE` (exit 1) rather than inventing a
  second staleness rule.
- H71 updates C-3861's snapshot SHA-256 to `2db48be1…` from this EXP instead
  of re-running the write.
- A future refresh task should re-check that the 44 identity moves stay
  `TODO.md`-only; a move in `docs/format/*.md` alongside a citation edit is
  the normal review case, not an anomaly.

## Reproduction

```bash
grep -n "moved-only drift exits 0" tools/fn_audit.py >/dev/null
python3 tools/fn_audit.py --selftest                      # expected: OK, 49 checks
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet   # expected: exit 0
sha256sum docs/research/fn-audit-corpus-2026-11-16.json
# expected: 2db48be11b5088571e2dea345caef535265716fcb1333fd017ac62ecce8eb17d
```
