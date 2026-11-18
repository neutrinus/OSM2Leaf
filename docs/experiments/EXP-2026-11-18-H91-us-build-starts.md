# EXP-2026-11-18-H91: H87's counts were true at `381879b` and moved at merge

- **Status:** done
- **Date:** 2026-11-18
- **Sample:** `none (docs-only task)` — the numbers in H87's `Result`, its EXP and
  C-4101/C-4112 against `tools/fn_audit.py` at five revisions.
- **Tools:** python3 3.15.0; repo tools `tools/fn_audit.py` (`--selftest`),
  `tools/claims_check.py` (`--strict --count-check`), `tools/todo_check.py`
- **Claims:** C-4140–C-4141
- **Supersedes:** none
- **Superseded by:** none

## Question

H87's `Result` and C-4101 say `US_BUILD_STARTS` "stays `12`" and
`OK (70 checks, 0 failed)`; what do those two counts measure at the revisions
now on `main`, and which commit moved each one?

## Hypothesis

Both numbers were true where H87 measured them (`381879b`) and false at
`origin/main`, because later merges changed the list and the selftest. Every
count must name the revision and the command that prints it.
**Falsifier:** the counts measure the same at `381879b` and at `398db35`
(nothing moved, so no repair is needed), or — after the edit — no line in H87's
block, its EXP or C-4101 says the merged list is `12`, or a count has no
revision.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (docs-only task)`; `tools/fn_audit.py` `US_BUILD_STARTS` |
| SHA-256 | `none (docs-only task)` |
| Offset(s) / VA(s) | the `US_BUILD_STARTS` entries; 15 of them at `398db35` |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/fn_audit.py --selftest` (prints the check count), `git show` + `grep -c` (counts the list) |

## Method

1. **Sample and hash.** `tools/fn_audit.py` at five revisions on `main`:
   `2e0bed9` (H87 start), `381879b` (H87 record), `f1c8dbb` (H88),
   `e199373` (M1.22), `398db35` (M1.22 record fix). No image and no vendor
   bytes: the object measured is a Python `frozenset` and a selftest footer.
2. **Commands.** Run from the repo root; each revision is extracted with
   `git archive` so the working-tree tool cannot answer for it.
   ```bash
   for r in 2e0bed9 381879b f1c8dbb e199373 398db35; do
     d=$(mktemp -d); git archive "$r" tools | tar -x -C "$d"
     printf '%s entries=%s selftest=' "$r" \
       "$(git show "$r:tools/fn_audit.py" | sed -n '/^US_BUILD_STARTS/,/^})/p' \
          | grep -c '0x[0-9A-Fa-f]\{8\}')"
     python3 "$d/tools/fn_audit.py" --selftest | tail -1
     rm -rf "$d"
   done
   git diff e199373 398db35 -- tools/fn_audit.py   # the four pool slots removed
   git log --oneline --reverse 381879b..398db35 -- tools/fn_audit.py
   python3 -c "import sys; sys.path.insert(0,'tools'); import fn_audit as fa; print(len(fa.US_BUILD_STARTS))"
   grep -c "will replace it" tools/fn_audit.py
   ```
3. **Controls.** *Positive*: `381879b` must print the numbers H87's text quotes
   (`12` entries, `70 checks`) — if it did not, H87's own record was wrong
   before any later merge. *Negative*: `2e0bed9`, H87's claim commit, must print
   the same `12`/`70`, so the `12` was in the tree before H87 touched it and H87
   did not move it; the repair is about pinning, not about H87's edit.
4. **Scope.** The `US_BUILD_STARTS` block and the `--selftest` footer of
   `tools/fn_audit.py` at those five revisions (six counting the working tree);
   the documents that quote them: TODO.md H87 `Result`, the H87 EXP,
   C-4101/C-4112. Excluded: every other claim row and every other tool, no
   image, no vendor bytes.
5. **Falsifier.** Stated in the Hypothesis, before the result.

## Observations

```
$ python3 --version
Python 3.15.0
$ for r in …; do …; done
2e0bed9 entries=12 selftest=selftest: OK (70 checks, 0 failed)
381879b entries=12 selftest=selftest: OK (70 checks, 0 failed)
e199373 entries=19 selftest=selftest: OK (72 checks, 0 failed)
f1c8dbb entries=12 selftest=selftest: OK (72 checks, 0 failed)
398db35 entries=15 selftest=selftest: OK (72 checks, 0 failed)
$ git show 398db35:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'
15
$ python3 -c "…; print(len(fa.US_BUILD_STARTS))"      # working tree 9beb6a4
15
$ grep -c "will replace it" tools/fn_audit.py
0
$ git log --oneline --reverse 381879b..398db35 -- tools/fn_audit.py
f1c8dbb fix: fn_audit --corpus reports a missing image instead of a traceback
e199373 feat: run the POINT walkers and the chunk engine on US 2011 code
398db35 fix: M1.22 record after navigator review (typed number, false limit, over-broad skip)
$ git diff e199373 398db35 -- tools/fn_audit.py
-    # M1.22: not function starts, but US pool slots the M1.22 census cites
-    # when it records which literal named which address.  They are skipped for
-    # the same reason as the starts (the EU head has no such start at these
-    # VAs), and recording them keeps the docs base at INSIDE 0.
-    0x004444D0,  # EU-looking start the raw US engine VA falls inside
-    0x0041DA5C,  # ditto, for the US nth reader
-    0x0041C2E0,  # ditto, for the US skip walker
-    0x0041E5E4,  # ditto, for the US dispatcher
$ git show 398db35:tools/fn_audit.py | grep -c '0x004444D0\|0x0041DA5C\|0x0041C2E0\|0x0041E5E4'
0
```

`git merge-base --is-ancestor` confirms all five revisions are on `main`; the
H87 EXP's own sample revision `857c9a7` prints the same `12`/`70` as `381879b`.

## Interpretation

- **FACT:** `381879b` prints `12` entries and `OK (70 checks, 0 failed)`, so
  H87's two numbers were true where H87 measured them, and C-4100's `12` is
  still correct for that revision.
- **FACT:** the list moved at `e199373` (12 → 19: the three POINT-walker starts
  plus four pool slots) and settled at `15` when `398db35` removed the four
  pool slots; `15` is what `origin/main` `9beb6a4` ships.
- **FACT:** the check count moved at `f1c8dbb` (70 → 72, H88's two
  `--corpus`-missing-image cases), the next `tools/fn_audit.py` touch after
  `381879b` (`git log --oneline --reverse 381879b..f1c8dbb -- tools/fn_audit.py`
  lists only `f1c8dbb`, which is `git rev-list --count 381879b..f1c8dbb` = `3`
  commits and `2` non-merge commits later) — not at
  `e199373` (H91's original Goal/Precheck attributed it to M1.22 and read `15`
  at `381879b`; this pass corrected both — see Corrections). Same for H88's
  C-4112: `72` holds from `f1c8dbb` on.
- **IMPLICATION:** no behaviour change. `fn_audit` skips the same 15 US VAs
  before and after the doc edit; the repair is quote discipline, which is what
  H92 turns into a check.

## Conclusion

`US_BUILD_STARTS` is 12 at `381879b` (H87) and 15 at `398db35`/`9beb6a4`;
`fn_audit --selftest` is `OK (70 checks, 0 failed)` at `381879b` and
`OK (72 checks, 0 failed)` from `f1c8dbb` on. H87's `Result`, its EXP and
C-4101/C-4112 now say exactly that, each count next to its revision and
command; the tool-side guard for the shape is H92.

## Reproduction

```bash
for r in 381879b f1c8dbb 398db35; do
  d=$(mktemp -d); git archive "$r" tools | tar -x -C "$d"
  printf '%s entries=%s selftest=' "$r" \
    "$(git show "$r:tools/fn_audit.py" | sed -n '/^US_BUILD_STARTS/,/^})/p' \
       | grep -c '0x[0-9A-Fa-f]\{8\}')"
  python3 "$d/tools/fn_audit.py" --selftest | tail -1; rm -rf "$d"
done
# expected: 381879b entries=12 … OK (70 checks, 0 failed)
#           f1c8dbb entries=12 … OK (72 checks, 0 failed)
#           398db35 entries=15 … OK (72 checks, 0 failed)
```

## Follow-ups

- [ ] H92 (already open) adds the mechanical `--prose-counts` guard for this
  shape; H91 does not add a second check (its `Stop:` says so).

## Falsifier result

- **Scoped (the Done when's surfaces).** The pattern `stays` + backticked `12`
  has `0` hits in H87's block, its EXP and C-4101:
  `{ sed -n '/\*\*H87 —/,/Claims: C-4100/p' TODO.md; cat
  docs/experiments/EXP-2026-11-17-H87-us-build-comment.md; grep '^| C-4101'
  docs/research/claims.md; } | grep -c 'stays `12`'` prints `0`.
- **Literal whole-file.** After round 2 `grep -c 'stays `12`' TODO.md
  docs/research/claims.md` prints `TODO.md:2` / `claims.md:0`: H91's `Goal`
  (line 963) and H92's `Precheck` (line 977, another owner's block). Both are
  quotations of the defect, not assertions about the merged list, so the
  literal count can never reach `0` on this board — which is why round 2
  replaced H91's `Falsifier` with the scoped check above.

## Corrections after navigator review

The navigator returned CHANGES on four required items plus four non-blocking
ones; all are applied here.

- **Goal attribution.** H91's Goal said the 70→72 selftest move came from
  "M1.22 added the two H88 cases". Verified false: `f1c8dbb` (H88) is the 70→72
  commit and is an *ancestor* of `e199373` (M1.22), and `e199373` leaves the
  footer at `72`. Attribution changed M1.22 → `f1c8dbb` in the Goal.
- **Precheck revision.** The old Precheck claimed `381879b` prints `15`; it
  prints `12` (`15` first appears at `398db35`). The Precheck now reads
  `398db35` → `15` and `381879b` → `12`, with the command for each. Both fixes
  are outside the original literal Scope ("Inputs, Observations, Reproduction");
  this pass widened the Scope to the whole H87 EXP and records them here.
- **Falsifier.** Replaced the unsatisfiable literal whole-file grep (it counts
  its own definition lines: H91 Goal/Falsifier and H92's Precheck) with the
  scoped three-surface check this record's "Falsifier result" section already
  runs and reports `0`.
- **H87 EXP Conclusion command.** The `grep -c` I added had no pattern (exit
  `2`); replaced with the six-VA pattern, which prints `6` at `381879b`.
- **H87 EXP `git diff` snippet.** The elided `…` line is replaced by the eight
  removed lines verbatim plus `git show 398db35:… | grep -c` → `0`.
- **Scope wording.** TODO.md H91 Scope widened from "(Inputs, Observations,
  Reproduction)" to the whole H87 EXP, with a note that the task authorises the
  edit to an append-only record.
- **Measured, not assumed.** `git merge-base --is-ancestor f1c8dbb e199373`
  exits `0`; `git show 381879b:… | sed -n '/^US_BUILD_STARTS/,/^})/p' |
  grep -c '0x[0-9A-Fa-f]\{8\}'` prints `12`; the same at `398db35` prints `15`.

**Round 2: APPROVED, no blocking items.** The two non-blocking wording fixes
are applied: the Goal's "two commits later" is now the measured
`git rev-list --count 381879b..e199373` = `6` (`4` non-merge), and this
record's "one commit after" is now "the next `tools/fn_audit.py` touch" with
`git rev-list --count 381879b..f1c8dbb` = `3` (`2` non-merge).

**For H92's owner:** H92's `Precheck` (TODO.md line 977) quotes this task's old
`stays `12`` line and a measured revision `3d79bcc`; both are stale once H91
merges, so H92 must re-point them at the post-H91 tree. Recorded here, not in
H92's block (one task per PR).

## Open follow-ups

- [ ] H92 re-points its Precheck after H91 merges (above).
