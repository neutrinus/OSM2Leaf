# EXP-2026-11-16-H72: `fn_audit` gate on `candidates`/`leaf` and `va` normalisation

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `archive/head256.img` (EU 2011 firmware head, 256 MiB) — SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
- **Tools:** python3 3.13.1; repo `tools/fn_audit.py` (this change)
- **Claims:** C-3930–C-3939
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `fn_audit`'s `--corpus` gate react to the two verdict components H69 left
out of `verdict_differs` — an `AMBIGUOUS` row whose candidate set changes and a
`GAP` row whose `leaf` flag flips — and does `va` hex padding manufacture
spurious `new`/`gone`?

## Hypothesis

`compare_live`'s `verdict_differs` compares only `class` and `true_start`
(H69), so an `AMBIGUOUS` row that gains an `INSIDE` candidate and a `GAP` row
whose `leaf` flips are invisible to the gate; `_row_key` compares the raw `va`
string, so `0x900000` and `0x00900000` are different keys. Adding a candidate-set
and `leaf` comparison and a canonical `va` key makes the gate fail on the first
two and stop printing new/gone on the third.

**Falsifier:** with the change applied, (i) an unchanged-candidates `AMBIGUOUS`
row is reported as a verdict change (would turn benign drift red), or (ii) the
unchanged real corpus stops exiting 0, or (iii) the padding fixture still prints
`new`/`gone`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (symlinked from the work image outside the repo) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Corpus | `docs/research/fn-audit-corpus-2026-11-16.json`, SHA-256 `ddd113f84228ff85af85fb633beba8dd70ed5dc072b52a542af1511ee0102a1a` (313 rows) |
| Tool / version | `python3 3.13.1` |
| Repo tool | `tools/fn_audit.py` |

## Method

1. **Sample and hash.** The EU 2011 firmware head above; the frozen corpus above
   (313 rows: `START 229, INSIDE 0, CORRECTED 23, GAP 29 (leaf 29), AMBIGUOUS 0,
   UNMAPPED 32`).
2. **Commands.** All runnable from the repo root; the fixtures are in
   `tools/fn_audit.py --selftest`, no image needed for them.

   ```bash
   # fixtures (the four H72 cases)
   python3 tools/fn_audit.py --selftest

   # the unchanged real tree stays exit 0 (moved-only is H69 prose drift)
   python3 tools/fn_audit.py archive/head256.img \
       --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
   sha256sum docs/research/fn-audit-corpus-2026-11-16.json
   ```

   The pre-fix control was produced by taking `git show origin/main:tools/fn_audit.py`
   beside the current support modules and running the same `audit_corpus` cases
   (candidate gain, GAP leaf flip, pure-padding). That script is reproduced below
   so the numbers are re-derivable:

   ```python
   import contextlib, io, os, sys
   sys.path.insert(0, sys.argv[1] + "/tools")
   import fn_audit as F
   T = F.Table(F.BUILD_A, {"synth.dll": [(0x900000, 0x10, 0x10)]})
   class Stub: pass
   s = Stub(); s.tables = [T]; s.leaf_of = lambda m, b, va: None
   cid = F.Citation(0x900000, "doc.md:3", "const")
   live = [(cid, F.classify([T], 0x900000, None))]
   rows = F.snapshot_rows(live)                 # canonical va + true_start
   doc = {"tool": "fn_audit", "snapshot_version": F.SNAPSHOT_VERSION,
          "scope": "docs", "image": "synth.img", "image_sha256": "0" * 64,
          "files": ["doc.md"], "rows": [dict(rows[0], va="0x900000")]}
   doc["summary"] = F.snapshot_summary(doc)
   F.collect = lambda scope="docs": ([cid], ["doc.md"])
   F.audit = lambda c, i: list(live)
   buf = io.StringIO()
   with contextlib.redirect_stdout(buf):
       rc = F.audit_corpus(doc, s, quiet=True, live_check=True)
   print("rc=", rc); print(buf.getvalue())
   ```

3. **Controls.** *Positive:* the unchanged real corpus must still exit 0
   (moved-only). *Negative:* an `AMBIGUOUS` candidate gain, a `GAP` leaf flip,
   and a pure-padding `va` each must (or must no longer) print the corresponding
   diagnostic; the benign unchanged-candidate fixture must stay exit 0.
4. **Scope.** `tools/fn_audit.py` `compare_live`/`verdict_differs`, `_row_key`,
   `snapshot_summary`, `corpus_fix_list`, `load_corpus`; the committed snapshot is
   unchanged and not refreshed (313 rows / 112 unique VAs). No other tool.
5. **Falsifier.** Above.

## Observations

Pre-fix (`origin/main`, cycle-7 QA repro, `/tmp/opencode/qa7/h72_repro.py`):

- Case A, frozen `AMBIGUOUS` candidates benign, image/live resolves `INSIDE`
  (`is_failure=True`): `audit_corpus` rc **0**, empty output.
- Case B1, stored `GAP leaf=True`, image `leaf=False`: rc **1** — but the message
  is `row class disagrees with the image` (that is `corpus_class_drift`, already
  present).
- Case B2, image and stored `leaf=True`, live verdict `leaf=False` (decoupled):
  rc **0**, empty output.
- Case C, pure padding (`va` `0x900000` vs live `0x00900000`, `true_start` equal):
  rc **1**, `CORPUS STALE: 1 new / 1 gone / 0 moved`.

Post-fix (this branch):

- Case A: rc **1**, `CORPUS STALE: 1 verdict change(s)`.
- Case B1: rc **1**, `row class disagrees with the image` **and** `CORPUS STALE:
  1 verdict change(s)`.
- Case B2: rc **1**, `CORPUS STALE: 1 verdict change(s)` (the new guard fires;
  the state is unreachable through one `--corpus` process, see Interpretation).
- Case C: rc **0**, no `new`/`gone`; `_row_key` frozen == live ==
  `("doc.md", 3, "0x00900000", "const")`.
- `python3 tools/fn_audit.py --selftest`: 58 checks, 0 failed (was 53).
- Real corpus: `CORPUS DRIFT: 0 new / 0 gone / 124 moved`, exit **0**; snapshot
  SHA-256 still `ddd113f8…102a1a`.

## Interpretation

- **FACT:** `verdict_differs` now treats an `AMBIGUOUS` candidate-set change and
  a `GAP` `leaf` flip as a verdict change (exit 1), and `_row_key` collapses
  padding so it cannot create `new`/`gone`. `snapshot_summary`'s `unique_va` and
  `corpus_fix_list` key through the same canonical `_canon_va`.
- **FACT:** the fix is falsifiable: reverting just the two comparisons and the
  key in a copy makes the three new negative fixtures fail (3 failed) while the
  unchanged-candidates fixture stays green.
- **OBSERVED / honesty note on the `leaf` half:** a stored-vs-image `leaf`
  mismatch was already caught before this change by `corpus_class_drift` (case
  B1, exit 1); `corpus_class_drift`'s leaf check is kept. A *live-only* leaf flip
  (case B2) cannot occur through the CLI today because, inside one `--corpus`
  process, the live rows and the stored rows classify against the same
  `Image` + `leaf_lookup`, so the image leaf the stored row is checked against is
  the same one the live verdict sees. The `leaf` comparison in `verdict_differs`
  is therefore a **latent, future-proof guard** for a future where the live and
  stored leaf sources diverge (e.g. M1.26 `--scope l3` adding a different leaf
  source), **not** a fix for a defect reachable today. It is shipped because it
  is cheap and self-tested, not because a live bug was observed.
- **OBSERVED:** the committed snapshot is `AMBIGUOUS 0`, so the candidate-set
  hole is latent on the frozen corpus for the same reason; the fixture proves
  the guard works for the rows M1.26 will add.
- **UNKNOWN:** whether M1.26 will introduce a leaf source that diverges from the
  image; if so, case B2 becomes reachable and this guard is what catches it.

## Conclusion

`tools/fn_audit.py` `--corpus` now fails (`CORPUS STALE` / verdict change, exit
1) when an `AMBIGUOUS` row's candidate set changes or a `GAP` row's `leaf`
flips, and `va` padding no longer manufactures `new`/`gone`. The unchanged
committed corpus and snapshot are untouched and still exit 0. The `leaf`
comparison is documented as a latent guard rather than a live-bug fix. Claims
C-3930–C-3934 record the reproduced behaviour; the rest of the block is
reserved.

## Reproduction

```bash
python3 tools/fn_audit.py --selftest
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet   # exit 0
```

## Follow-ups

- [ ] M1.26 (`--scope l3`) adds `AMBIGUOUS` rows; re-run `--corpus` on the
      refreshed snapshot so the candidate-set guard is exercised on real rows,
      and confirm no new leaf source diverges (case B2 stays latent otherwise).
- [ ] The cycle-7 QA `_row_key` observation also split `snapshot_summary` and
      `corpus_fix_list`; both now use `_canon_va` (covered here, no separate
      task).
