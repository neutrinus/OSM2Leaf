# EXP-2026-11-06-H1: Repair the claim ledger and the EXP index

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** none read. No vendor data was opened; the reference image SHA-256
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` is named
  only to identify the sample the cited records describe.
- **Claims:** C-600–C-604 (C-600…C-602 re-affirmed, C-603–C-604 new)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `docs/research/claims.md` and `docs/experiments/README.md` be brought to
"one ID per claim, every proposed claim registered, every record indexed"
without editing experiments, renaming files, or deleting a claim row?

## Hypothesis

None / exploratory. The repair is a bookkeeping pass: no data claim is
re-decided, only IDs and the index are reconciled.

## Inputs

| Item | Value |
| --- | --- |
| Ledger | `docs/research/claims.md` (working tree, after PR #17) |
| Index | `docs/experiments/README.md` |
| Experiment dir | `docs/experiments/EXP-*.md` |
| Tooling | `python3 tools/claims_check.py`, `python3 tools/selftest.py` |
| Vendor data | none |

## Method

```bash
# 1. duplicate ID check (prints only duplicates; empty = one ID per claim)
awk -F'|' '/^\| C-[0-9]+ /{gsub(/^ +| +$/,"",$2); if (seen[$2]++) print $2}' \
  docs/research/claims.md

# 2. claim-row count
awk -F'|' '/^\| C-[0-9]+ /{n++} END{print "claim rows:",n}' \
  docs/research/claims.md

# 3. index coverage: every EXP file exactly once, no stale links
python3 - <<'PY'
import re, pathlib
from collections import Counter
idx = pathlib.Path('docs/experiments/README.md').read_text()
files = {p.name for p in pathlib.Path('docs/experiments').glob('EXP-*.md')}
links = re.findall(r'\]\((EXP-[^)]+\.md)\)', idx)
print("files", len(files), "links", len(links), "unique", len(set(links)))
print("missing", sorted(files - set(links)))
print("dupe", [k for k, v in Counter(links).items() if v > 1])
PY

# 4. ledger contract tool and the repo self-test
python3 tools/claims_check.py
python3 tools/selftest.py
```

## Observations

### Duplicate IDs

At the start of this run each of `C-070`, `C-110`, `C-543`, `C-546` and
`C-558` occurred exactly **once** in `claims.md`; the duplicate state named in
the task no longer reproduced because PR #17 had already touched the file. The
awk check printed nothing before and after the edits.

During the pass, 17 rows carried the same `Was proposed as C-xxx in EXP-…`
sentence twice (a merge artefact); each now carries it once. `C-543` carried a
wrong annotation (`Was proposed as C-542`); the IMF-checker claim was never
proposed under another ID, so the annotation was removed. No row was deleted
and no claim wording was changed.

### Registered rows

Rows added (all appends; existing rows untouched):

| ID | Source | Reason |
| --- | --- | --- |
| C-603 | H1 | Index lists every record once (was 69 of 83) |
| C-604 | H1 | Registration summary for the rows below |
| C-720 | EXP-2026-11-05-M2.1 | Task block had no ledger row |
| C-890 | EXP-2026-11-05-M4.1 | Task block had no ledger row |
| C-900 | EXP-2026-11-05-M4.2 | Task block had no ledger row (negative) |
| C-930 | EXP-2026-11-05-M4.5 | Task block had no ledger row; registered `RETRACTED` after H6 |
| C-960 | EXP-2026-11-06-M4.8 | EXP proposed C-960 and asked for registration |
| C-1010 | EXP-2026-11-05-M4.13 | Task block had no ledger row |
| C-1100 | EXP-2026-11-05-M5.8 | Task block had no ledger row |
| C-1120–C-1129 | EXP-2026-11-06-M6.4 | EXP says "H1 registers" |
| C-1130–C-1138 | EXP-2026-11-06-M6.8 | EXP reserves the block and adds no rows |
| C-1720–C-1726 | EXP-2026-11-06-H6 | EXP says "rows to add … by H1" |

Dropped, with the one-line reason:

- `C-1110–C-1119` (M6.3): plan only; the EXP states "no ledger rows added" and
  carries no claim text, so there is nothing to register.
- `C-1139` (M6.8): a process claim saying that task added no row; registering it
  would make it false.

`C-930` is the only new row that did not survive its own experiment: H6, written
in parallel, showed that M4.5 analysed the FAT root directory rather than
`MMAIN001.DAT`. The row is kept as `RETRACTED` with `Superseded by C-1721`,
per the retraction rule, instead of being removed.

### Index

| Measure | Before | After |
| --- | --- | --- |
| EXP records on disk | 83 | 86 (H6, M6.4 and this record appeared during the run) |
| Rows in `README.md` | 69 | 86 |
| Files missing from index | 14 | 0 |
| Duplicate links | 0 | 0 |
| Stale links | 0 | 0 |

Two records (H6, M6.4) were created by parallel sessions after the index audit
started; they were indexed in the same pass, as was this record.

The duplicate-numbered pairs (`EXP-2026-11-05-29` ×2, `EXP-2026-11-05-35` ×2)
keep their file names and are listed with the slug in the link text
(`…-29 · static-closed` / `…-29 · l1-l2-validators`,
`…-35 · ce-romhdr` / `…-35 · us-card-validator`); a note under the index
heading says why. No experiment file was renamed.

### Contract tool and self-test

```text
$ python3 tools/claims_check.py
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
claims_check: OK

$ python3 tools/selftest.py --only claims_check,tool:claims_check,tool:cerom,tool:section4,tool:hddinfo,tool:imf_check,tool:diff_years,tool:rdstm_schema,tool:header_block,tool:profile_validate,tool:rdstm_record,tool:tile_diff,tool:coord,tool:mmain,tool:name_strings
...
passed=15 failed=0 skipped=0 total=15 time=1.20s
selftest: OK
```

The full `python3 tools/selftest.py` run reported `passed=25 failed=1
skipped=20 total=46` because of `tool:osm_ingest FAIL`: that file is untracked
and was created by a parallel M5 session during this run (`git ls-tree HEAD
tools/osm_ingest.py` is empty). It is outside H1's file scope; the 15 suites
that cover this task pass.

## Interpretation

- **FACT:** the ledger has one row per claim ID (awk prints nothing) and 580
  claim rows after the pass (545 before, 35 appended).
- **FACT:** every `Claims:` block that named a free ID (M4.8 C-960, M6.8
  C-1130–C-1139, M6.4 C-1120–C-1129, H6 C-1720–C-1726) has ledger rows, except
  the two drops listed above.
- **OBSERVED:** the duplicate IDs from the task description were already gone
  in the working tree; only the doubled annotations remained.
- **UNKNOWN:** whether `C-1130–C-1138` planning claims survive contact with
  hardware; they are registered as their authors wrote them.

## Conclusion

`docs/research/claims.md` gains C-603, C-604 and 33 task rows, and loses only
duplicate annotation text. `docs/experiments/README.md` gains a duplicate-number
note, slug-distinct link labels and 17 missing rows (49–51, the task records,
H6, M6.4 and this record). `tools/claims_check.py` and the H1 suites stay green.
No format document, tool or experiment file was changed by this task.

## Follow-ups

- [ ] Extend `tools/claims_check.py` (out of H1's file scope) to assert the
      index coverage checked by the script above, so a new EXP cannot land
      unindexed.
- [ ] M6.3 owns C-1110–C-1119; add those rows when the plan becomes a result.
- [ ] `tools/mmain.py` still parses the FAT root directory (H6 follow-up); the
      `C-930` retraction does not change that tool.
- [ ] When H7's `IMG256` run lands, update its index status from "run pending".
