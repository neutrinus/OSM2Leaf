# EXP-2026-11-06-H12: Fifth product review — ten merged tasks audited, board re-planned

- **Status:** done (review; no format fact created)
- **Date:** 2026-11-06
- **Sample:** no vendor image was read. The audit is of the repository at
  `origin/main` = `5191f07` plus the ten task records named below; every
  command below is reproducible from the repo alone. Sample SHA-256 values are
  quoted from the audited EXPs, not re-measured here.
- **Claims:** none — a review creates no format claim. Four colliding task
  reservations were re-issued (C-2300…C-2349); no ledger row changed.
- **Supersedes:** none
- **Superseded by:** none

## Question

Do the ten task results merged since the fourth pass (2026-11-06) match their
experiment records and the board text, what did they leave unfinished, and
which of the follow-ups in the 149 experiment records are real work that the
board does not yet name?

## Hypothesis

None / exploratory. Two outcomes are expected: at least one `Result` line that
claims more than its EXP proves (the parallel-work model invites this), and a
set of follow-ups that no task covers because the task that wrote them owned
only its own block.

## Inputs

| Item | Value |
| --- | --- |
| Board | `TODO.md` at `origin/main` `5191f07` |
| Ledger | `docs/research/claims.md` (`tools/claims_check.py`) |
| Tool registry | `tools/selftest.py` (63 suites after the M4.12 tool merged) |
| Audited records | H11, M1.2c, M2.14, M4.20, M5.12b, M5.13, M6.12, M8.A1, M8.A4, M8.A5, M8.A7, M8.E1, M8.E1b, M9.8, M9.9 |
| Follow-up sweep | all `docs/experiments/EXP-*.md` (149 files, 114 with open follow-ups) |
| Vendor data | none |

## Method

```bash
git checkout main && git pull                     # 48431e2 -> 5191f07
python3 tools/selftest.py                         # 45 passed / 0 failed / 18 skipped
python3 tools/claims_check.py                     # 0 duplicate IDs, 0 unregistered
for f in docs/experiments/EXP-*.md; do ...        # extract "## Follow-ups" items
grep -oP 'Claims: C-\d+–C-\d+' TODO.md | sort | uniq -d
grep -c "| C-XXXX |" docs/research/claims.md      # is a reserved block populated?
```

Each merged task was checked in three steps: (1) does the `Result` line state
a number the EXP contains; (2) is the EXP's own status honest about what was
not run; (3) does the board text that depends on it still hold.

## Observations

### Task-by-task

| Task | `Result` says | EXP says | Verdict |
| --- | --- | --- | --- |
| H11 | matrix of 30 rows, linked from roadmap/README | same; **explicitly** "survey only, promotes nothing" | matches |
| M1.2c | VAs recorded, codec not ported, handed to M8.E1 | same; adds `DECOMP_BLK` port + `cerom.py decompress` follow-ups | matches (and M8.E1b later corrected the endianness of the peer result) |
| M4.20 | US `DRSTR001` rebuild byte-identical at `0x1ae0` | stored entry-name case (`ltntbl.dat`), US 7,456 B + EU | matches |
| M5.12b | label slot copied verbatim, source order kept | **synthetic fixture only**, no factory image on the host | matches, but the board implication ("M5.12 rebuild reports the label") was never measured |
| **M5.13** | board line said `done (planning)`; EXP delivers a tool | `imgpatch.py` verified on a synthetic fixture (46 checks); **C-2027 = `UNKNOWN`**, S1/S2 images never built | **overstated on the board**: the S-chain looked ready |
| M6.12 | procedure written, unverified | same; 5 bench follow-ups | matches |
| M8.A1 | build env `-M ze0` lists the machine | env verified; **the gate fails by design** until M8.A2; 42 self-test checks | matches (the `Result` was already corrected in the same PR) |
| M8.A4 | series applies, compiles, instantiates; kernel MMU UNVERIFIED | same; 8.2.7 `dc->reset` fix recorded | matches |
| M8.A5 | patch applies, compiles, qtest-checked; boot UNVERIFIED | same; adds the observation that `m8a4-0002/0003` "target 8.2.0 and fail on 8.2.7" | **contradicts M8.A4** (see below) |
| M8.A7 | `run.sh` + `gdb-ze0.py` (30 checks), stand-in QEMU only | same | matches |
| M8.E1b | LE re-derivation, VAs restored, runtime decode not executed | same; bit-level positive controls | matches; C-1600/C-1603 correctly marked superseded |
| M9.8 | 1 PASS, 5 BLOCKED, exit 3 when nothing runs | same; blocked targets cannot claim a verdict | matches |
| M9.9 | docs current | same; 5 follow-ups | matches |

### The one contradiction that needs a run

M8.A1 recorded that a parallel run stopped at `m8a4-0002` with rejected hunks
in `hw/sh4/meson.build`/`Kconfig` (exit 1, fail-closed). M8.A5 recorded that
`m8a4-0002/0003` "target 8.2.0 and fail on the pinned 8.2.7 tree". M8.A4
recorded `git apply --check` rc=0 for all three on pristine 8.2.7, and the
`m8a4-0003` header in the repo now reads "Base: QEMU 8.2.7". The most likely
explanation is that the series was rebased between the two observations, so
the M8.A5 sentence is stale rather than wrong. It cannot be settled by reading:
one `build.sh --force` over `patches/*.patch` settles it. That is now part of
**M8.A2**'s `Done when`, and the patch order it produces must be recorded.

### Board defects found

| Defect | Consequence | Fix |
| --- | --- | --- |
| Four claim blocks issued twice (`C-1840`, `C-1950`, `C-1960`, `C-1970`) | two tasks would write rows into the same IDs | M4.16b→C-2300, M4.16c→C-2310, M4.16d→C-2320, M5.11→C-2330, M5.1b→C-2340 |
| H11's gap table hands G1 `C-2290–C-2299`, which M8.E1b took later | a gap task would collide on merged rows | G1→C-2370 … G8→C-2440 in `reader-coverage.md` and `TODO.md` |
| H11 says G8 is `M9.18` (conclusion) and `M9.19` (table) | two IDs for one task | `M9.18` used; the ambiguity is recorded in the matrix |
| M5.8's `Depends`/`Goal`/`Input`/`Done when`/`Claims` fields sit inside M4.8c's block | `C-1100–C-1109` looked like M4.8c's while M4.8c also carries `C-1990–C-1999`; M5.8 had no fields | fields moved back to M5.8 |
| `M5.13` read `done (planning)`, while M6.5/M6.6 depend on "M5.13 (S1/S2 image)" | the nearest milestone looked blocked only by hardware | status now says "done (tool; the real S1/S2 images are M5.13b, C-2027 UNKNOWN)" |
| `roadmap.md` still says "Last updated 2026-11-05" and lists full-system QEMU under "What not to do yet" | a new agent would skip the M8 workstream that now has a build env | header + three Gate-0 rows + that bullet corrected; the rest is H13 |
| `tools/README.md` has no `imgpatch` and no `qemu-ze0` row | two merged tools are undiscoverable | **H13** |
| No check ever ran the five pinned `harness.py verify` tiles, the extra `coredll` ordinals, or the qemu-ze0 self-tests | pins without a run are documentation | **H14** |

### Follow-up sweep (149 records, 114 with open items)

Classification of every open follow-up item:

| Class | Count (approx.) | Action |
| --- | --- | --- |
| Already a task, or the task's own `Done when` | majority | none |
| Retired lead (pre-CE-ROM-TOC address work, spare-card matrices) | ~45 | left retired; one new retired-leads row (`mkcard` fresh build for S1/S2) |
| Hardware/bench | ~20 | already M6.2/M6.5–M6.11/M6.12 |
| **Real, uncovered** | **17** | turned into tasks (below) |

The 17 uncovered items and where they went:

| Source (EXP / task) | Follow-up | Task |
| --- | --- | --- |
| M5.13, M5.10 | build S1/S2 on the real US image; minimal-diff build for a changed tree | **M5.13b**, **M5.20** |
| M1.2c, M8.E1b | port `DECOMP_BLK 0x8803a384`; confirm `DECOMP_ALLOC` prototype | **M1.2f** (prototype check folded into M8.E1) |
| M1.9 | resolve the last 149 slots via A-side exporters | **M1.10** |
| M3.4, M3.9, M3.10, M8.E1b | "needs SH-4 disassembly tooling" (four records) | **M1.11** |
| H11 G1–G8 | reader/L3/writer gaps | **M9.17**, **M3.18**, **M4.21**, **M5.16**, **M5.17**, **M5.18**, **M5.19**, **M9.18** |
| EXP-2026-11-05-40, -03, H6 | header `0x180`, `DRSTR` `0x18c`, `BICON001` version | **M4.22** |
| M5.1 | node tags (POI/address/place) into IMF | **M5.1c** |
| M9.3, M9.5, M9.9 | firmware entry kind, `engine_hook`, `ghidra/l3_run.py`, READMEs | **M9.20** |
| H7, H8, H9, M8.A7 | pins and self-tests never run | **H14** |
| roadmap/`tools/README.md` | doc debt | **H13** |

### Verification output

```
$ python3 tools/selftest.py 2>&1 | tail -2
passed=45 failed=0 skipped=18 total=63 time=6.23s
selftest: OK

$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK
```

Ledger spot-check: the blocks the ten tasks reserved all have rows —
`C-1230`, `C-1260`, `C-1270`, `C-1290`, `C-1700`, `C-2010`, `C-2020`,
`C-2030`, `C-2290` each return 1 match. No ledger work is outstanding.

## Interpretation

- **FACT:** nine of the ten merged results match their EXP; the tenth (M5.13)
  is a correct tool result whose board line (`done (planning)`) hid that its
  own `C-2027` is `UNKNOWN`. The S1/S2 images do not exist.
- **FACT:** the ledger is current (no missing rows for any block reserved
  since the fourth pass) and the tool registry grew from 61 to 63 suites with
  no failures.
- **FACT:** four claim blocks were issued twice and one H11 gap block was
  already taken; all five are re-issued above the highest used block (`C-2299`).
- **OBSERVED:** the follow-up lists are the project's richest untapped source —
  114 of 149 records have open items, and 17 of them name work no task owned.
  The largest cluster is the writer side: five file families a Poland card
  needs have no generator at all.
- **HYPOTHESIS:** the M8 patch-order contradiction is a stale sentence, not a
  broken series (the 0003 banner and M8.A4's rc=0 both say 8.2.7). M8.A2's
  single `build.sh --force` is cheap enough to prove it either way.
- **UNKNOWN:** whether S1/S2 will be accepted by the unit; that is L4 and
  needs Marek's hardware after the software gate.

## Conclusion

The board now names every uncovered follow-up as a task, issues unique claim
blocks, and stops presenting the S-chain as ready. The nearest milestone is one
run (**M5.13b**) away from existing; the software gate (M3.11/M3.2b → M9.10/
M9.11 → M9.12) and M9.6 are unchanged and still first in the queue alongside
it. No format knowledge changed, so no format doc and no claim row was touched.

## Follow-ups

- [ ] **M5.13b** — build `us_S1.img`/`us_S2.img`; this is the next action on
      the whole board.
- [ ] **M8.A2** — one `build.sh --force` run settles the patch-order
      contradiction recorded above.
- [ ] H13/H14 — the doc and verification debt this review found.
- [ ] Re-run this audit (as H15) after the next ten merges; the sweep script
      and the four checks in "Method" are the whole procedure.