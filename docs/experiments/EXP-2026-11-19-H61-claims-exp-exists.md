# EXP-2026-11-19-H61: every cited EXP name must resolve to a record

- **Status:** done
- **Date:** 2026-11-19
- **Sample:** `docs/research/claims.md` at `fa7c8af` (H61 claim commit on top of
  the H58 merge `eef8cc2` and the H62 merge `8e3b99f`), SHA-256
  `161198b4bec9aed16f3253b1d085369acc1a599538a5955c90a21599b072f79f`, and the
  `docs/experiments/` listing at the same commit (341 files, 337 `EXP-*.md`)
  (no vendor bytes: the ledger and the file names are the corpus)
- **Tools:** `python3 3.13.18`; `tools/claims_check.py` (this change, `--selftest` 50 checks)
- **Claims:** C-3810–C-3815
- **Supersedes:** none
- **Superseded by:** none

## Question

Which ledger rows name an `EXP-YYYY-MM-DD-…` record that does not exist as a
record file in `docs/experiments/`?

## Hypothesis

The precheck's 8 rows (C-1900–C-1906 cite `EXP-2026-11-08-M4.8b-poi-refs`,
which exists only as a `.tsv`; C-3033 cites a `.tsv` companion by its suffix)
are the whole defect set under a rule that needs an `.md` record, or a
`companion:`-marked data file next to one.

**Falsifier:** the rule names a row whose EXP is a real `.md` record (cited
bare, with `.md`, or by a stem whose record carries a `-slug`/`-2` suffix;
e.g. C-3170–C-3175 with `….md`), or misses C-1900 or C-3033.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `docs/research/claims.md`, `docs/experiments/` |
| SHA-256 | `161198b4bec9aed16f3253b1d085369acc1a599538a5955c90a21599b072f79f` (claims.md) |
| Offset(s) / VA(s) | none (ledger rows) |
| Tool / version | `python3 3.13.18` |
| Repo tool | `tools/claims_check.py` (`exp_name_reason`, `unresolved_exp_names`) |

## Method

1. **Sample and hash.** As above; 2,383 claim rows, 1,672 of them name an
   `EXP-<date>-…` token (`grep -cE "^\| C-.*EXP-[0-9]{4}" docs/research/claims.md`).
2. **Commands.**

   ```bash
   grep -cE "^\| C-.*EXP-[0-9]{4}" docs/research/claims.md
   python3 tools/claims_check.py --selftest
   python3 tools/claims_check.py | grep 'unresolved EXP names'
   python3 tools/claims_check.py | grep '^  NOEXP'
   python3 tools/claims_check.py; echo "exit $?"
   python3 tools/claims_check.py --strict; echo "exit $?"
   python3 tools/claims_check.py --strict-evidence; echo "exit $?"
   cd /tmp && python3 /home/user/OSM2Leaf.task-h61-claims-exp-exists/tools/claims_check.py | grep 'unresolved EXP names'
   ```

   The rule, for every `EXP-\d{4}-\d{2}-\d{2}-[A-Za-z0-9.-]+` token in a row
   (trailing `.` stripped), against the file names in `REPO_ROOT/docs/experiments/`:
   a bare or `.md` token must match an `.md` record by exact stem or stem
   plus `-…` (`-slug`, `-2`); else `no-record` if a non-`.md` file carries
   the name, `missing` otherwise. A `.tsv`/`.json`/`.csv`/`.txt` token must
   exist (`missing`), have an `.md` record whose stem prefixes it
   (`companion-orphan`), and follow `companion:` in the row
   (`companion-unmarked`). Record contents are never read.
3. **Controls.** *Positive* (selftest): a missing name, an unmarked `.tsv`
   (C-3033 shape), a `.tsv`-only name (C-1900 shape) and a marked orphan
   companion fail. *Negative*: a bare and a `.md`-suffixed record, a marked
   `.tsv` beside its record, a stem whose record is `…-point-reader-2.md`, and
   the old `EXP-2026-11-05-38` numbering all pass. On the real ledger,
   C-3170–C-3175 (`EXP-2026-11-09-M5.31-mkcard-reconcile-resize.md`) must
   not be named.
4. **Scope.** All 2,383 rows, any column; 337 `EXP-*.md` records plus 2
   non-`.md` `EXP-*` files. Not checked: that a record contains the section
   a row cites (reviewer's job), and `EXP-…`/`EXP-YYYY…` placeholders, which
   the date regex does not match.
5. **Falsifier.** As stated above, before the result.

## Observations

- `--selftest`: `claims_check selftest: OK (50 checks)`.
- `unresolved EXP names: 8 (warning; --strict-evidence fails)`:
  `NOEXP C-1900`…`C-1906 EXP-2026-11-08-M4.8b-poi-refs (no-record)` (7 rows)
  and `NOEXP C-3033 EXP-2026-11-09-M2.18-hddinfo-predictor-variants.tsv
  (companion-unmarked)`.
- C-3170–C-3175 are not named.
- Exit codes: default `0`, `--strict` `0` (what `tools/gate.py` runs),
  `--strict-evidence` `1`.
- Run from `/tmp`: the same `unresolved EXP names: 8` (names resolve from
  `REPO_ROOT`, not the working directory).

## Interpretation

- **FACT:** the 8 unresolved rows are exactly the precheck's 8; the falsifier
  did not fire.
- **FACT:** H58 merged its opt-in `--strict-evidence` (its Stop: 347 legacy
  command rows, and `gate.py` runs `--strict`), so H61 reuses that flag as its
  error switch rather than `--strict`; no second flag and no second parser.
  The task's "`--strict` exits 1" therefore reads `--strict-evidence` here.
- **OBSERVED:** the task's Input calls `poi-refs.tsv` "the `.tsv`-only record
  the rule must allow", while its Precheck and Done-when require C-1900 to be
  named. The Done-when was followed: a `.tsv` is data, not a record, so the
  7 rows need an `.md` record (or a `companion:` pointer to one) from the
  task that owns M4.8b.
- **HYPOTHESIS:** with 8 rows (≪ H58's 347) this rule alone could be an error
  under `--strict` once those 8 rows are fixed.

## Conclusion

`tools/claims_check.py` prints `unresolved EXP names: N` and one `NOEXP` line
per row on every run, carries `unresolved_exp_names` in `--json`, and fails
under `--strict-evidence`. Default and `--strict` verdicts are unchanged. The
8 rows stay as they are (their owners fix the record, rule 17).

## Reproduction

```bash
python3 tools/claims_check.py | grep 'unresolved EXP names'      # expected: 8 (at fa7c8af)
python3 tools/claims_check.py --strict-evidence; echo "exit $?"  # expected: exit 1
```

## Follow-ups

- [ ] M4.8b owner: write an `.md` record for `poi-refs` (or cite the `.tsv` as
      `companion:` of an existing record) for C-1900–C-1906; mark C-3033's
      `.tsv` as `companion:`.
- [ ] H53/H66: move this rule under `--strict` once the 8 rows resolve.
