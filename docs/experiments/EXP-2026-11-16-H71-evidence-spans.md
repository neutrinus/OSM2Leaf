# EXP-20261116-H71: C-3860/C-3861/C-3864 evidence spans are runnable

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** EU2011 head `archive/head256.img`, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` (256 MiB,
  git-ignored per rule 11; `fetch_image.py --image IMG256`)
- **Tools:** python3 3.13.1; repo tools `tools/fn_audit.py`,
  `tools/claims_check.py`
- **Claims:** C-3920–C-3929
- **Supersedes:** none (repairs the evidence cells of C-3860/C-3861/C-3864)
- **Superseded by:** none

## Question

Do C-3860, C-3861 and C-3864 carry evidence a reader can run as written, and
does every value they state match what the command prints?

## Hypothesis

The three cells elide their commands (`… --fix-list`, `--write-snapshot …`,
`--corpus … --quiet`), and C-3861's stored snapshot hash plus C-3864's quoted
staleness counts are stale. Falsifier: after replacing each elision with the
real path/flag, a re-run does not print the stated value (or the hash does not
match the committed file).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (EU2011 head) |
| SHA-256 | `92aa525d…007f9` |
| Image / file | `docs/research/fn-audit-corpus-2026-11-16.json` (313-row docs snapshot) |
| SHA-256 | `ddd113f8…102a1a` (H69 refresh) |
| Offset(s) / VA(s) | none (corpus audit) |
| Tool / version | python3 3.13.1 |
| Repo tool | `tools/fn_audit.py`, `tools/claims_check.py` |

## Method

1. **Sample and hash.** The head above; the snapshot is committed and its hash
   printed below.
2. **Commands.** From the repo root:

   ```bash
   python3 tools/fn_audit.py archive/head256.img --scope docs --quiet
   python3 tools/fn_audit.py archive/head256.img --fix-list
   python3 tools/fn_audit.py archive/head256.img --scope docs --write-snapshot /tmp/opencode/snap.json
   sha256sum /tmp/opencode/snap.json
   python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
   cp TODO.md /tmp/opencode/TODO.bak
   printf '\n- [ ] **H99 — synthetic staleness probe**\n  - Status: open · Owner: — · Critical: no · Goal: fn 0x0041c7e8 probe\n' >> TODO.md
   python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
   cp /tmp/opencode/TODO.bak TODO.md
   awk -F'|' '/^\| C-386[014] \|/{print $NF}' docs/research/claims.md | grep -c '…'
   ```

3. **Controls.** *Positive*: the `--corpus` run on the unmodified tree reports
   `CORPUS DRIFT: 0 new / 0 gone` and exits 0, matching the claim summary.
   *Negative*: one probe line appended to `TODO.md` makes the same command
   print `CORPUS STALE: 1 new / …` and exit 1.
4. **Scope.** The three claim rows only. The l3 overlay and the other claim
   rows are out of scope.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

```
$ python3 tools/fn_audit.py archive/head256.img --scope docs --quiet
fn_audit: START 229, INSIDE 0, CORRECTED 23, GAP 29 (leaf 29), AMBIGUOUS 0, UNMAPPED 32
$ python3 tools/fn_audit.py archive/head256.img --fix-list | wc -l
0
$ sha256sum docs/research/fn-audit-corpus-2026-11-16.json
ddd113f84228ff85af85fb633beba8dd70ed5dc072b52a542af1511ee0102a1a
$ … --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet   # unmodified
CORPUS DRIFT: 0 new / 0 gone / 125 moved
$ … --corpus … --quiet   # TODO probe appended
CORPUS STALE: 1 new / 0 gone / 125 moved      # exit 1
$ awk -F'|' '/^\| C-386[014] \|/{print $NF}' docs/research/claims.md | grep -c '…'
0

# a fresh write today: 313 rows, summary identical, differs from the committed
# file only in moved line numbers
$ sha256sum /tmp/opencode/snap.json
9afe3f7dff438dcd0f999cf5bd95817c1e85d36f6d9c9473665dae4fc167398e
```

## Interpretation

- **FACT:** the three evidence cells now name the exact path/flag; no `…`
  remains in their evidence column (the two remaining `…` in C-3860/C-3861 are
  abbreviated hashes inside the claim text, which the done-when excludes).
- **FACT:** C-3861's stored hash `4606aa2a…` was the pre-H69 snapshot; the
  committed file is `ddd113f8…` (H69's deliberate refresh).
- **OBSERVED:** C-3864's quoted `CORPUS STALE: 1 new / 0 gone / 0 moved` is
  now `1 new / 0 gone / 125 moved`; the new count is the current prose drift,
  the verdict (`STALE`, exit 1) is unchanged.
- **UNKNOWN:** none.

## Conclusion

The three rows are runnable and their stated values match the commands.
C-3861 carries the committed `ddd113f8…` hash with a note that a fresh write
differs only in moved lines (`9afe3f7d…`); C-3864 carries the real staleness
counts. No tool changed.

## Reproduction

```bash
python3 tools/fn_audit.py archive/head256.img --fix-list | wc -l   # 0
sha256sum docs/research/fn-audit-corpus-2026-11-16.json           # ddd113f8…
awk -F'|' '/^\| C-386[014] \|/{print $NF}' docs/research/claims.md | grep -c '…'  # 0
```

## Follow-ups

- [ ] H66: extend the `bad_evidence` rule to the whole ledger once these three
      rows are clean.
