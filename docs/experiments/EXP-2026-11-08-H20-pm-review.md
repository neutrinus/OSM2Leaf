# EXP-2026-11-08-H20: Ninth product review — the compression premise was wrong

- **Status:** done (review; no format fact created)
- **Date:** 2026-11-08
- **Sample:** no vendor image read in this task. The subjects are the 15 EXP
  records dated 2026-11-06…-11-08 that landed after `476dfb0`, plus
  `docs/research/claims.md` at `2405a66`.
- **Tools:** `git`, `gh`, `python3 3.14` (stdlib), `tools/selftest.py`,
  `tools/claims_check.py`.
- **Claims:** none — a review creates no format claim. The retraction below is
  of a **process rule**, not of a claim row; the claim rows that matter
  (C-2124/C-2126 → C-2128/C-2129) already exist and were written by the M3.11
  pass-2 EXP.
- **Supersedes:** the fifth, sixth and seventh pass readings of "why the reader
  searches failed" (EXP-2026-11-06-H15, -H17); their facts stand, the diagnosis
  does not.
- **Superseded by:** none

## Question

Sixteen results landed in two days (23 commits). Do their `Done when` states
match the board, and is the sixth-pass conclusion — "reader searches are gated
by the CE codec because 56 % of build A is compressed" — still true after
M3.11 pass 2 found the walker?

## Hypothesis

None / exploratory. The sixth pass already carried a same-day correction
pasted into `TODO.md` by the M3.11 agent; this review checks whether the rest
of the board, `AGENTS.md` and `reader-coverage.md` were corrected with it.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at `origin/main` `2405a66` |
| New records | M2.16, M1.10, M3.11-pass2, H14, H16, M1.11, M3.19, M4.2, M4.3, M5.13b, M5.1b, M5.1c, M9.14, M9.17, M9.21 |
| Ledger | `docs/research/claims.md` (C-2080…C-2557 in scope) |
| Live branch | `origin/claude/m5.12c-poi-copies` (M5.12c, not merged) |
| Vendor data | none |

## Method

```bash
git log --oneline 476dfb0..origin/main          # 23 commits, 15 new EXPs
gh pr list --state open                         # 0 before the review
git branch -r                                   # one live task branch
python3 - <<'PY'                                # claim-block collision check
# task block -> Claims: C-x..C-y, duplicates and blocks above C-2290
PY
python3 tools/selftest.py                       # 51 passed / 0 failed / 18 skipped
python3 tools/claims_check.py                   # clean
```

For each record: does the `Result`/`Conclusion` state a status that matches the
board, does its `Done when` check pass, and does it cite anything that is not on
`main`?

## Observations

### 1. The sixteen results

| Task | Outcome on the board | Note |
| --- | --- | --- |
| M5.13b | **done** | S1 byte-level no-op; S2 changes only the POINT010 pair + size; `cardcheck` PASS; 17,737 diff ranges inside POINT010 clusters. Limits: cluster base from the write offset, not an independent BPB read; zlib 1.3.2 not 1.3.1 |
| M3.11 (pass 2) | **done** (walk) | walker `fn 0x003f5194`; runs from ROM bytes in PySh4 on the real US page; 9/9 sampled records match `parse_page`; name split to M3.11c, byte order to M3.11b |
| M9.21 | **done** | `PySh4` little-endian + `bt/s`/`bf/s`; this is what made the M3.11 L3 run possible |
| M5.1b | **done** | real Dolnośląskie PBF ingests unchanged; counts reproduced; negative control fails with E011 on exactly three ways |
| M5.1c | **done** | POI/address/place records in IMF; `imf_check --strict` gate; W007–W010 for writer-side defects |
| M1.11 | **done** | `sh4dis.py` LE decoder; reproduces prologue, flag test, 4 pool values; fails loudly on BE; `sh4xref` no longer needs objdump |
| M1.10 | **done** | 846/846 import slots named; the B-only resolver under-reported 149 |
| H14 | done | 4/5 tiles + LEV3456R reproduce; **`B30R048R` raises** → pin untrusted |
| H16 | done | `fetch_image.py`, pinned/resumable; 2016 hash still missing |
| H13 | done | `tools/README.md` rows + roadmap stage model |
| M3.19 | **blocked** | eight of nine published counts reproduce; the ninth exposed a **wrong description** in M3.11 pass 1 (register AND, not immediate) → M3.20 |
| M4.2 | **blocked** | gate: 0 of 9 candidate fields resolve a road identity; OSM verified but not correlated |
| M4.3 | **blocked** | OSM restriction decodes; tile side has no documented regulation layout → needs a new task |
| M9.14 | **blocked** | runner cannot declare a module-VA target (M9.20) |
| M9.17 | **blocked** | same cause (M9.20) |
| M2.16 | done | no factory card carries `HDD_CHK.ATT`; `sub_0001e3f4` is a crypto-context check (CRLF + ≥8 B in `0x80`), not `memcmp` |

### 1b. Two tasks merged while this review ran

`M9.20` (L3 plumbing, `562215a`) and `M9.6` (map-code compare, `ff8720d`)
landed after the audit above. Consequences applied in the same commit:
M9.14 and M9.17 are re-opened per rule 15 (their only blocker was M9.20), and
M2.4 no longer waits for a comparator. The table in §1 records the state at
`2405a66`, before those merges.

### 2. The premise that has to go

`AGENTS.md`, `TODO.md` rule 14 and `reader-coverage.md` all said, in effect:
"56.2 % of build A is compressed and `Navi.exe` is 75 % compressed, so a reader
search over uncompressed sections covers only a quarter of the module."

C-2128 (measured by M3.11 pass 2) says the opposite about **code**:

| Measure | Value |
| --- | --- |
| Executable section bytes, build A | 22,767,466 B, **0 compressed** |
| All section bytes / compressed | 53,725,980 B / 30,212,810 B = `.data` + resources |
| Compressed seed of the miss | the walker `fn 0x003f5194` was in `sec0` all along |

The first M3.11 negative was therefore a **heuristic miss**: it searched for
`cmp/eq #0x60`, `#0x68`, `and #0xf7` and `mov.b @(1,Rm)`, but the firmware
packs type and length into one native `u16` (`w>>10`, `w & 0x3ff`, `0xfc00`
escape — C-2542). A correct search of the *complete* code set produced "not
found" because the signature came from `refer.md`, not from the code.

Two process conclusions follow, and both are now in rule 14:

1. a precheck must separate executable from data bytes (M1.12 prints both);
2. a negative must name the **signature** it tested and where the signature came
   from. A doc-derived signature is the weakest source; an L3 run or the
   writer's inverse is stronger.

### 3. Consequences applied to the board

- **M3.2b and M3.13 re-opened** (`Depends: —`, not M1.2f). Their "caller/parser
  in sec1" blockers were the same error; "no static caller" now reads as an
  indirect call through a `.data` pointer, which is exactly how the POINT
  walker is reached.
- **M3.14–M3.16/M3.18 prechecks rewritten**: they no longer say "if compressed,
  depend on M1.2f". They require a structural signature and a signature-family
  stop.
- **M1.2f keeps only its real job** (M1.3, M1.4, `.data` tables).
- **M9.20 promoted to critical**: it is the only reason M9.14 and M9.17 merged
  without a verdict, and M9.11/M9.13 need the same hook.
- **M5.12c marked in progress** with its live branch; M1.13/M5.21 no longer cite
  an EXP that is not on `main`, and M5.21 no longer attributes the slot rule to
  C-2355 (that row is the imgpatch EOC fix; the slot rule belongs to
  M5.12c's C-2040–C-2049).
- **M3.19/M3.20 moved** from the H section into M3 (they were filed under
  Housekeeping).
- `B30R048R`'s byte-identical pin is marked untrusted (**M9.22**).
- `M1.11`'s `Input` no longer says `sh4xref` shells out to objdump (it decodes
  through `sh4dis.py` now).

### 4. New tasks from uncovered follow-ups

| Source | Follow-up | Task |
| --- | --- | --- |
| M1.11 | duplicated LE reader, unpinned `mov.w @(disp,PC)`, no independent oracle | **M1.14** |
| M1.10 | confirm an `XGLDLL`/`OSMDLL` name at a call site | **M1.10b** |
| M2.16 | crypto dispatch, 0x582–0x5e8 range, generator | **M2.17** |
| M4.3 | section-2 regulation/connectivity reader (kinds `0x2046`/`0x3e4`) | **M4.23** |
| H14 | `B30R048R` rebuild assertion | **M9.22** |
| H16 | 2014/2016 hashes and local-vs-pin check | **H21** |

### 5. Board hygiene checks

- No duplicate claim block; highest row is C-2557, so M1.14/M1.10b/M2.17/
  M4.23/M9.22 take C-2590…C-2639.
- No `in progress` task without a live branch: M5.12c is the only one and its
  branch exists.
- One live remote branch, zero open PRs (after the 2026-11-08 cleanup); the
  M5.12c branch is intentionally kept.

### 6. Verification

```
$ python3 tools/selftest.py 2>&1 | tail -2
passed=51 failed=0 skipped=18 total=69
selftest: OK
$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK
```

## Interpretation

- **FACT:** the compression premise was wrong for code. Every executable section
  of build A is readable; the walker was in `sec0` and was missed by a
  doc-derived signature (C-2128/C-2129/C-2542).
- **FACT:** two of the sixteen results (M9.14, M9.17) merged `blocked` for one
  tooling reason (M9.20), not for twelve different ones. That is a good sign:
  the blockers now converge.
- **FACT:** the nearest milestone moved from "software" to "hardware": S1 and S2
  exist and pass L1; only Marek's unit is missing.
- **OBSERVED:** the first real writing limit appeared (M5.12c: 5 of 136 pages do
  not refit; stock zlib 0.8 % larger). That is a *data* limit, not a tooling
  one, and it is now M1.13/M5.21.
- **HYPOTHESIS:** with the corrected signature rule, M3.2b and M3.13 will land
  in one session each, because both already have their access path and a call
  engine (`0x41c7e8`, `0x0040114e`).
- **UNKNOWN:** whether the walker's name accessor needs the SDL chain
  (`0x003cd910`) or a different accessor; M3.11c decides.

## Conclusion

The board now states the compression fact correctly, re-opens the two tasks
whose blockers it invalidated, promotes the one harness task that blocks two
verdicts, and files six follow-ups as tasks. No format doc changed: the format
facts (C-2128, C-2540–C-2546) were already written by the M3.11 pass-2 record
and the ledger. The rules changed: rule 14 now asks for the signature, not for
a decoder.

## Reproduction

```bash
python3 tools/point_walk_l3.py sections IMG256     # expect: 0 compressed executable sections
P=/home/marek/projekty/leafre-work/m5.13/factory/REFER001
python3 tools/point_walk_l3.py walk IMG256 --cmp "$P/POINT010.DAT.cmp" \
    --ind "$P/POINT010.DAT.ind" --page 0x840ba0     # expect: matches parse_page
python3 tools/selftest.py                          # expect: 51 passed, 0 failed (69 suites at this run)
```

## Follow-ups

- [ ] **M9.20** → M9.14/M9.17 (first two real reader verdicts on our files).
- [ ] **M3.11c** → M9.10 name half; **M3.2b/M3.13** re-runs with `sh4scan`.
- [ ] **M1.13/M5.21** — the page-length/slot pair, now on the critical path for
      any POI edit.
- [ ] Re-run this audit after the next batch; the two checks that found
      everything here are "does any task cite an EXP that is not on `main`?" and
      "is every `blocked` caused by a task that exists?"