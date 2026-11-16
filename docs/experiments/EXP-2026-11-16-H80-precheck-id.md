# EXP-2026-11-16-H80: H71's Precheck selects claim rows by line range

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (docs-only task)` — the sample is `TODO.md` and
  `docs/research/claims.md` at the tree below; no vendor bytes.
- **Tools:** python3 3.15; repo tools `tools/todo_check.py`
- **Claims:** C-4030–C-4039
- **Supersedes:** none
- **Superseded by:** none

## Question

H71's `Precheck:` line is `sed -n '2802,2807p' docs/research/claims.md | grep
-nE '…|\.\.\.'`. A Precheck is a command a later agent runs to decide whether a
done task's premise still holds. Does that line range still select the rows H71
touched, and if not, what selector survives later row insertions?

## Hypothesis

The standing rule (AGENTS.md / retro-9) is *select by ID, never by line*. Line
ranges rot: M1.26/H74/H75 added rows above C-3860/61/64, so `2802–2807` now
holds a different claim series. **Falsifier:** if the range still lands on the
three rows, the Precheck is not broken and nothing should change.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `docs/research/claims.md`, `TODO.md` (H71 block) |
| SHA-256 | `none (docs-only task)` |
| Offset(s) / VA(s) | claims rows C-3860, C-3861, C-3864 |
| Tool / version | python3 3.15 |
| Repo tool | `tools/todo_check.py` |

## Method

1. **Sample.** The two prose files at `origin/main` before this task
   (`5d2dd23`), plus H71's landing commit `caff825`.
2. **Commands.**
   ```bash
   # what the old range holds now (the rot)
   sed -n '2802,2807p' docs/research/claims.md | cut -c1-40
   sed -n '2802,2807p' docs/research/claims.md | grep -cE 'C-386[014]'

   # where the three rows are, by ID
   grep -nE '^\| C-386[014] \|' docs/research/claims.md | cut -d: -f1

   # H71's own elided-span condition, at the landing commit and now
   for ref in caff825 HEAD; do
     git show "$ref:docs/research/claims.md" \
       | awk -F'|' '/^\| C-386[014] \|/{print $NF}' | grep -c '…'
   done
   python3 tools/todo_check.py
   ```
3. **Controls.** *Positive*: the new ID selector prints the three rows.
   *Negative*: the old range prints `0` matches for `C-386[014]`, which is the
   failure being repaired.
4. **Scope.** The H71 block's `Precheck:` line only (plus the H80 block's own
   before/after note). No claim row, no tool, no other H71 field.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

```
$ sed -n '2802,2807p' docs/research/claims.md | cut -c1-30
| C-3790 | ...
| C-3791 | ...
| C-3792 | ...
| C-3793 | ...
| C-3794 | ...
| C-3795 | ...
$ sed -n '2802,2807p' docs/research/claims.md | grep -cE 'C-386[014]'
0
$ grep -nE '^\| C-386[014] \|' docs/research/claims.md | cut -d: -f1
2824
2825
2828
$ for ref in caff825 HEAD; do git show "$ref:docs/research/claims.md" | awk -F'|' '/^\| C-386[014] \|/{print $NF}' | grep -c '…'; done
0
0
```

The row count selected by ID is `3`; the elided-span count is `0` both at H71's
merge (`caff825`) and today. So H71's *result* already satisfied its own
Done-when; only the Precheck's line range was stale.

## Interpretation

- **FACT:** the old range `2802–2807` now holds C-3790–C-3795, not C-3860/61/64;
  it matches `0` of the rows H71 touched, so a later agent would read the
  Precheck as evidence the task is moot.
- **FACT:** selecting by ID lands on `2824`, `2825`, `2828`, and the elided-span
  condition prints `0` there — so the repaired Precheck both finds the rows and
  states the condition the Done-when uses.
- **IMPLICATION:** no measurement changed. The H80 "Done when" asks a *repair*
  (ID selector + note), and running it as written prints the count (`3`) and
  `0` elided spans.

## Conclusion

H71's Precheck now selects C-3860/61/64 by claim ID and checks the same
elided-span condition as its Done-when; running it as written prints the row
count and `0`. Line numbers are documented as not-an-anchor.

## Reproduction

```bash
grep -nE '^\| C-386[014] \|' docs/research/claims.md | cut -d: -f1
# 2824  2825  2828
awk -F'|' '/^\| C-386[014] \|/{print $NF}' docs/research/claims.md | grep -c '…'
# 0
python3 tools/todo_check.py
# todo_check: OK
```
