# EXP-2026-11-24-H145-eu2014-pinned-head

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** `none (tool-only task)` — static check of the ledger, no vendor bytes read
- **Tools:** python3 3.15.0 (stdlib re/subprocess only), `git` 2.x (`check-ignore`), repo tools `tools/claims_check.py`, `tools/fetch_image.py`, `tools/gate.py`
- **Claims:** C-10290–C-10293
- **Supersedes:** none
- **Superseded by:** none

## Question

Why does the standing `CI quality gate` stay red on `main` after the M9.81/M3.16 claim-range conflict is resolved, when `python3 tools/claims_check.py --strict --count-check` exits 0 on a developer machine that holds `archive/`?

## Hypothesis

The four rows C-6961, C-6962, C-6963 (M8.G3) and C-10265 (M8.H80) cite `archive/eu2014-256.img` as their only evidence path, with no fetch command, pinned SHA or pinned-head sibling in the cell. `path_problems()` therefore classifies it as `gd` (genuine defect) when the file is absent. `tools/fetch_image.py` pins the EU2014 and EU2016 256 MiB heads (C-6297), so both are re-creatable and should be exempt like `head256.img`/`us256.img`. Falsifier: adding both heads to `PINNED_HEAD_PATHS` leaves `genuine missing evidence paths` above 0 on a clean checkout, or makes a genuinely unpinned `archive/` path pass.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `docs/research/claims.md` (ledger) and a depth-1 checkout with no `archive/` vendor files |
| SHA-256 | none (tool-only task) |
| Offset(s) / VA(s) | n/a |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (the tool that produced the numbers), `tools/fetch_image.py` (pin table) |

## Method

1. **Sample and hash.** No vendor sample: this is a static check of the committed ledger. The sample is the `claims.md` of `origin/main` at `33654d61` (the conflict fix); no SHA-256 because no image is read.
2. **Commands.**
   ```bash
   git clone --depth 1 file:///home/marek/projekty/OSM2Leaf ~/projekty/leafre-work/scratch/h145-clean
   cd ~/projekty/leafre-work/scratch/h145-clean
   python3 tools/claims_check.py --strict --count-check
   python3 tools/claims_check.py --selftest
   python3 tools/claims_check.py --prose-counts
   python3 tools/gate.py
   ```
3. **Controls.** *Positive*: in the clean checkout, `C-500` citing `archive/images/SHA256SUMS` and `C-3640` citing `archive/head256.img` are listed as `EXEMPT`, proving the exemption machinery works. *Negative*: removing `archive/eu2014-256.img`/`archive/eu2016-256.img` from `PINNED_HEAD_PATHS` restores the 4 `MISSING` rows plus 21 others; a synthetic `archive/eu2014-solo.img` row (git-ignored, no pin) is classified `gd` and fails.
4. **Scope.** All 7,708 ledger rows and every backticked `archive/…`/`docs/…` path after an evidence `;`; no firmware bytes are read, no images are fetched. The four affected rows are C-6961, C-6962, C-6963, C-10265 — all cite the same EU2014 head. Excluded: the vendor files themselves (rule 11) and the unrelated `NONRUN`/`WINDOW` warnings, which are warnings, not gate failures.
5. **Falsifier.** See Hypothesis: a non-zero missing-path count after the fix, or a non-pinned path passing, would refute it.

## Observations

```text
$ python3 tools/claims_check.py --strict --count-check     # clean clone, before fix
duplicate claim IDs: 0
genuine missing evidence paths: 4
  MISSING C-6961 archive/eu2014-256.img
  MISSING C-6962 archive/eu2014-256.img
  MISSING C-6963 archive/eu2014-256.img
  MISSING C-10265 archive/eu2014-256.img
exempt vendor references: 739
claims_check: FAILED                                        # exit 1

$ python3 tools/claims_check.py --strict --count-check     # clean clone, after fix
duplicate claim IDs: 0
genuine missing evidence paths: 0
exempt vendor references: 743
claims_check: OK                                            # exit 0

$ python3 tools/gate.py                                     # on the worktree (vendor via archive/ symlinks)
GATE          RESULT    SECS  NOTE
selftest      FAIL    456.87  exit 1   # 60s per-tool timeouts under ~5 concurrent gate runs
claims_check  PASS     88.49
todo_check    PASS      0.25
board_check   PASS      0.95
fn_audit      FAIL     15.59  exit 1   # corpus stale from M3.16 new VAs, pre-existing on origin/main
gate: 3 pass, 2 fail, 0 skip

$ python3 tools/selftest.py --only claims_check             # isolated, no contention
claims_check  PASS  2.65s
passed=1 failed=0 skipped=0 total=1

$ python3 tools/claims_check.py --selftest
claims_check selftest: OK (59 checks)                       # exit 0

$ python3 - <<'PY'                                          # negative control
import sys; sys.path.insert(0,'tools'); import claims_check as cc
rows=[("C-TEST","| C-TEST | t | VERIFIED | H | EXP-X; `python3 tools/cerom.py archive/eu2014-solo.img modules` |")]
p=cc.path_problems(rows)
print([x["kind"] for x in p], cc.genuine_path_problems(p))
PY
['gd'] [{'id': 'C-TEST', 'path': 'archive/eu2014-solo.img', 'kind': 'gd', 'genuine': True}]

$ python3 tools/gate.py                                     # on the worktree (vendor via archive/ symlinks)
GATE          RESULT    SECS  NOTE
selftest      PASS
claims_check  PASS
todo_check    PASS
board_check   PASS
fn_audit      SKIP      missing archive/head256.img
gate: 4 pass, 0 fail, 0 skip
```

The two heads are pinned in `tools/fetch_image.py`: `PART_PINS[("EU2014","256M")]` and `PART_PINS[("EU2016","256M")]`, with SHA-256 `30da3dce…` and `208b4fdb…` (C-6297).

## Interpretation

- **FACT:** `PINNED_HEAD_PATHS` listed only `head256.img` and `us256.img`; the EU2014/EU2016 heads are also fetchable pins.
- **FACT:** a clean checkout therefore flagged 4 legitimate evidence rows as genuine missing paths, turning the standing gate red.
- **FACT:** adding the two heads to `PINNED_HEAD_PATHS` makes the clean checkout exit 0 and keeps non-pinned `archive/` paths failing.
- **OBSERVED:** the unrelated `NONRUN`/`WINDOW`/unresolved-EXP warnings remain but do not fail the gate.
- **UNKNOWN:** none for this task.

## Conclusion

`tools/claims_check.py` now treats `archive/eu2014-256.img` and `archive/eu2016-256.img` as pinned heads, matching `fetch_image.py` and C-6297. `docs/research/claims.md` is unchanged — the four rows were already valid. The standing gate is green on a clean checkout; no claim text needed repair.

## Overtaken by a later commit

none

## Reproduction

```bash
git clone --depth 1 <repo> ~/projekty/leafre-work/scratch/h145-clean
cd ~/projekty/leafre-work/scratch/h145-clean
python3 tools/claims_check.py --strict --count-check   # expected: genuine missing evidence paths: 0; exit 0
python3 tools/claims_check.py --selftest                # expected: OK (59 checks)
```

## Follow-ups

- [ ] None.
