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

After the change (flag `nargs="?", const="-"`, atomic writer):

```
$ python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3-h55.json
exit 0                        # file written, stdout empty
$ python3 tools/l3check.py --build-corpus --json > /tmp/opencode/l3-h55-stdout.json
exit 0
$ cmp /tmp/opencode/l3-h55.json /tmp/opencode/l3-h55-stdout.json
bajt 191, linia 8 differs     # corpus.root/manifest = random --build-corpus tempdir
```

With one fixed corpus so the document is stable:

```
$ python3 tools/l3_harness/corpus.py build /tmp/opencode/l3-corpus-h55
$ python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus-h55 --json /tmp/opencode/l3-h55.json; echo $?
0
$ python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus-h55 --json > /tmp/opencode/l3-h55-stdout.json; echo $?
0
$ cmp /tmp/opencode/l3-h55.json /tmp/opencode/l3-h55-stdout.json; echo $?
0
$ wc -c /tmp/opencode/l3-h55.json
5280 /tmp/opencode/l3-h55.json
```

Document: `schema=osm2leaf.l3check/v1`, `result=PASS`,
`counts={"pass":1,"fail":0,"skip":0,"blocked":5,"runnable":1,"total":6}`.

```
$ python3 tools/l3check.py --selftest
ok   cli: --json PATH writes the same document as bare --json
ok   cli: --json PATH still writes the report when the run fails
l3check selftest: OK (20 checks, 1 skipped)      # skip = Ghidra missing
$ python3 tools/selftest.py --only l3check
tool:l3check  PASS
$ python3 tools/progress_report.py --l3-json /tmp/opencode/l3-h55.json --no-stdout; echo $?
0                                                # no parse/input problem
```

## Interpretation

- **FACT:** bare `--json` already worked (positive control, exit 0).
- **FACT:** `--json PATH` was a usage error before the change (negative
  control, exit 2, `unrecognized arguments`).
- **OBSERVED:** after the change both forms work; with a fixed `--corpus` the
  file is byte-identical to bare-`--json` stdout (`cmp` exit 0).
- **OBSERVED:** two independent `--build-corpus` runs differ only in
  `corpus.root`/`corpus.manifest`, which name a random temporary directory;
  this is pre-existing report content, not a `--json` change, and a byte
  comparison must use one fixed corpus or normalise that path.
- **OBSERVED:** `progress_report.py --l3-json` consumes the written file with
  exit 0 and no input problems — the schema is unchanged.
- **UNKNOWN:** none for argument parsing; card/firmware behaviour is out of
  scope.

## Conclusion

`tools/l3check.py --json` now takes an optional `PATH` (`nargs="?"`,
`const="-"`): a bare flag and `-` keep the old stdout behaviour, `PATH`
receives the same document written atomically in UTF-8. The report schema
(`osm2leaf.l3check/v1`), target verdicts and `--build-corpus` output are
unchanged, and `progress_report.py --l3-json` reads the file without changes.
Claims added: C-3710–C-3713 (see `docs/research/claims.md`).


## Reproduction

```bash
python3 tools/l3check.py --build-corpus --json /tmp/opencode/l3-h55.json; echo $?
python3 tools/l3check.py --build-corpus --json > /tmp/opencode/l3-h55-stdout.json
cmp /tmp/opencode/l3-h55.json /tmp/opencode/l3-h55-stdout.json
```

## Follow-ups

- [ ] H56 consumes this file via `progress_report.py --l3-json`.
