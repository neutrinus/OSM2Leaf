# EXP-2026-11-15-H55: `l3check --json PATH` writes the report file

- **Status:** running
- **Date:** 2026-11-15
- **Sample:** none (tool-only task) — no card or firmware bytes are read;
  the L3 corpus is built synthetically by `tools/l3_harness/corpus.py`.
- **Tools:** `python3 3.13.1` (stdlib only); `tools/l3check.py`,
  `tools/progress_report.py`, `tools/selftest.py`.
- **Claims:** C-3710, C-3711, C-3712, C-3713
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `tools/l3check.py --json PATH` write its machine-readable report to a file
(and to stdout when PATH is `-`), while a bare `--json` keeps printing to
stdout, without changing the report schema or verdicts?

## Hypothesis

`--json` is declared `action="store_true"` (`tools/l3check.py`), so
`--json PATH` is an argparse usage error (exit 2). Making it
`nargs="?", const="-"` should accept both forms and write the identical
document to PATH. **Falsifier:** the file parses to a different document than
bare `--json`, or bare `--json` stops printing JSON, or a caller of the flag
(e.g. `progress_report.py --run-tools`, which passes `--json` with no value)
breaks.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (synthetic corpus from `tools/l3_harness/corpus.py`) |
| SHA-256 | n/a — no vendor data |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.13.1` |
| Repo tool | `tools/l3check.py` (the tool modified and measured) |

## Method

1. **Sample and hash.** No vendor sample; the corpus is the deterministic
   `--build-corpus` fixture. The defect is in argument parsing, not in bytes.
2. **Commands.**

   ```bash
   python3 tools/l3check.py --build-corpus > /tmp/opencode/l3-pre.out 2>&1; echo $?
   python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3-pre.json > /tmp/opencode/l3-pre2.out 2>&1; echo $?
   ```

3. **Controls.** *Positive*: bare `--json` prints the JSON document to stdout
   (exit 0). *Negative*: `--json PATH` must be rejected before the fix (exit
   2, `unrecognized arguments`), and must be accepted after it.
4. **Scope.** `tools/l3check.py` argument handling and one report document;
   the report schema (`osm2leaf.l3check/v1`), target verdicts and
   `--build-corpus` output are unchanged. Vendor data excluded (none needed).
5. **Falsifier.** See Hypothesis.

## Observations

Before the change (HEAD `1201fbe`):

```
$ python3 tools/l3check.py --build-corpus
exit 0                        # positive control: report printed
$ python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3-pre.json
exit 2
l3check.py: error: unrecognized arguments: /tmp/opencode/l3-pre.json
```

## Interpretation

- **FACT:** bare `--json` already works (positive control).
- **FACT:** `--json PATH` is a usage error before the change (negative control).
- **OBSERVED:** (filled after the change)
- **UNKNOWN:** none for the argument parsing; vendor/card behaviour is out of
  scope.

## Conclusion

(filled after the change)

## Reproduction

```bash
python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3-h55.json; echo $?
python3 tools/l3check.py --build-corpus --json > /tmp/opencode/l3-h55-stdout.json
cmp /tmp/opencode/l3-h55.json /tmp/opencode/l3-h55-stdout.json
```

## Follow-ups

- [ ] H56 consumes this file via `progress_report.py --l3-json`.
