# EXP-2026-11-20-H97: `l1l2_fixtures` names a coverage gap and gains `--require-covered`

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** none (tool-only task) — `tools/l1l2_fixtures.py` runs synthetic
  checks only and reads no vendor bytes, so there is no image/file hash to pin.
- **Tools:** `python3 3.15.0 / zlib 1.3.1.zlib-ng` (H9: byte-identical
  recompress unverifiable, reported as SKIP); `tools/l1l2_fixtures.py`,
  `tools/selftest.py`
- **Claims:** C-4250, C-4251, C-4252, C-4253, C-4254
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `tools/l1l2_fixtures.py` report a required L1/L2 category as "OK" when
that category has no runnable check at all, and can the verdict name that gap
(and optionally fail on it) without changing the default exit code that CI and
every open PR depend on?

## Hypothesis

`summarize()` sets `"ok": runnable_fail == 0` and publishes
`required_categories`/`missing_categories` but never consults them, so a
required category made entirely of `NOT COVERED` rows still yields
`ok=true` and exit 0. **Falsifier:** `--json` still shows `ok=true` with a
required category at zero runnable checks and no key naming that category.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only; no vendor data read or produced) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0`, `zlib 1.3.1.zlib-ng` |
| Repo tool | `tools/l1l2_fixtures.py` (pre-fix `origin/main` `ce5f34c`; fix on `task/h97-l1l2-verdict`) |

## Method

1. **Sample and hash.** No sample: this is a verdict/report change in an
   offline tool, so the only inputs are the committed registry and the tool
   source. The before/after JSON reports are scratch (not committed; a few KB).
2. **Commands.** Run as written from the repository root. "Before" = the tool
   as on `origin/main` `ce5f34c`; "after" = the tool on the task branch.

   ```bash
   W=~/projekty/leafre-work/scratch/h97

   # Before: a detached worktree at origin/main (the tool derives ROOT from
   # __file__, so a copied-out script would compute the wrong paths):
   git worktree add --detach "$W/pre" ce5f34c
   python3 "$W/pre/tools/l1l2_fixtures.py" --json "$W/l1l2-before.json" --no-stdout-md
   echo "before rc=$?"
   python3 -c "import json;s=json.load(open('$W/l1l2-before.json'))['summary'];print('ok',s['ok'],'missing',s['missing_categories'],'gaps',s.get('coverage_gaps','<absent>'),'counts',s['counts'])"
   git worktree remove --force "$W/pre"

   # After (task branch):
   python3 tools/l1l2_fixtures.py --json "$W/after.json" --no-stdout-md; echo "default rc=$?"
   python3 tools/l1l2_fixtures.py --require-covered --no-stdout-md; echo "require-covered rc=$?"
   python3 -c "import json;s=json.load(open('$W/after.json'))['summary'];print('ok',s['ok'],'covered',s['covered'],'gaps',s['coverage_gaps'])"
   python3 tools/l1l2_fixtures.py --selftest
   python3 tools/selftest.py --only l1l2_fixtures
   ```

   (The before worktree runs the pre-fix `summary`; its `coverage_gaps` key is
   absent, which is the defect. `tools/l1l2_fixtures.py` was byte-identical at
   `2e683be` and `ce5f34c` — `git diff 2e683be ce5f34c -- tools/l1l2_fixtures.py`
   is empty — so `ce5f34c` is a faithful pre-fix base.)
3. **Controls.**
   *Positive*: the selftest's synthetic registry with one runnable PASS per
   required category gives `coverage_gaps == []`, `covered == true`, and
   `--require-covered` exit 0.
   *Negative*: the synthetic `[PASS, SKIP, NOT COVERED]` registry leaves three
   required categories at zero runnable — `coverage_gaps` must name them, the
   default exit must stay 0, `--require-covered` must exit 1, and a synthetic
   runnable FAIL must still exit 1 under `--require-covered`. The markdown
   verdict must read `OK (3 required categories NOT COVERED)`.
4. **Scope.** The `summary`/Markdown contract of `tools/l1l2_fixtures.py` and
   its `--selftest` (30 checks). Not covered: the checks' own correctness
   (H26 owns the registry), filling the L1 synthetic row (H40/H41), and any
   CI wiring of `--require-covered` (H42).
5. **Falsifier.** Stated in Hypothesis: `ok=true` with a required category at
   zero runnable and no `coverage_gaps` key. The before-report is that state
   (`gaps <absent>`); the after-report must name the category.

## Observations

Before (`origin/main` `ce5f34c`, `l1l2-before.json`):

```
ok True missing [] gaps <absent> counts {'PASS': 7, 'FAIL': 0, 'SKIP': 1, 'NOT COVERED': 2}
```

After (`task/h97-l1l2-verdict`, `after.json`):

```
ok True covered False gaps ['L1 synthetic']
```

Command exits on the after tree:

```
default:          verdict=OK (1 required category NOT COVERED: L1 synthetic)  rc=0
--require-covered: verdict=OK (1 required category NOT COVERED: L1 synthetic)  rc=1
selftest:          l1l2_fixtures self-test: OK (30 checks)
selftest.py --only l1l2_fixtures: PASS
```

Per-category runnable counts in `after.json` (runnable = PASS+FAIL+SKIP):

```
L1 synthetic:    0 runnable, 1 NOT COVERED   -> gap
L2 DRSTR:        2 runnable, 0 NOT COVERED
L2 cmp/ind:      4 runnable, 0 NOT COVERED   (3 PASS + 1 SKIP)
L2 tile:         1 runnable, 1 NOT COVERED   -> covered (l2.tile.class-roundtrip)
L2 POI mutation: 1 runnable, 0 NOT COVERED
```

## Interpretation

- **FACT:** the pre-fix `summary` has no key that names a fully-uncovered
  required category; `ok` is `runnable_fail == 0` only.
- **FACT:** the `NOT COVERED` row count (2) and the fully-uncovered category
  count (1) differ. The two `NOT COVERED` rows are `l1.synthetic.cardcheck`
  (in `L1 synthetic`) and `l2.tile.harness-selftest` (in `L2 tile`); the second
  category is covered by `l2.tile.class-roundtrip`, which PASSes (M5.36). So
  the task's "two NOT COVERED categories" refers to two `NOT COVERED` *rows*,
  not two fully-uncovered categories.
- **OBSERVED:** the default exit is unchanged (0) while the verdict line now
  names the one real gap; `--require-covered` turns that gap into exit 1.
- **HYPOTHESIS:** once H40 adds a vendor-free L1 card builder,
  `coverage_gaps` will be empty and H42 can call `--require-covered` without
  blocking PRs.

## Conclusion

`tools/l1l2_fixtures.py` now publishes `coverage_gaps` (required categories
with zero runnable checks) and `covered`, names the gap in the human verdict
(`verdict=OK (N required … NOT COVERED: …)`), and adds an opt-in
`--require-covered` that exits 1 on a gap. The default exit and the existing
JSON keys are unchanged, so `l1l2-fixtures.yml` and every open PR keep the same
pass/fail behaviour. Today's one gap is `L1 synthetic` (H40/H41 own filling
it); `L2 tile` is no longer fully uncovered because M5.36 added a runnable
class round-trip. No fixture was invented here.

## Overtaken by a later commit

- `C-4254` (OBSERVED plan; `L1 synthetic` is the sole gap) | later H40 merge
  that makes `L1 synthetic` runnable | `coverage_gaps` becomes `[]`; the key
  and `--require-covered` stay (H97 Stop rule).

## Reproduction

```bash
python3 tools/l1l2_fixtures.py --json ~/projekty/leafre-work/scratch/h97/after.json --no-stdout-md; echo $?   # expected: verdict=OK (1 required category NOT COVERED: L1 synthetic), 0
python3 tools/l1l2_fixtures.py --require-covered --no-stdout-md; echo $?                                       # expected: same line, 1
python3 tools/l1l2_fixtures.py --selftest                                                                      # expected: OK (30 checks)
```

## Follow-ups

- [ ] H40/H41: make `L1 synthetic` runnable, then `coverage_gaps == []`.
- [ ] H42: call `--require-covered` in the L1/L2 CI once both gaps are filled.
