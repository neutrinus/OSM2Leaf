# EXP-2026-11-19-H58: the claims ledger reports non-runnable evidence

- **Status:** done
- **Date:** 2026-11-19
- **Sample:** `docs/research/claims.md` at `934d76e` (the H58 claim commit),
  SHA-256 `4d016ef5318a2e28ef7993435813b14adc81f434d2b7508742120ee41e77ad87`
  (no vendor bytes: the ledger is the corpus)
- **Tools:** `python3 3.13.18`; `tools/claims_check.py` (this change, `--selftest` 47 checks)
- **Claims:** C-3770–C-3775
- **Supersedes:** none
- **Superseded by:** none

## Question

How many `VERIFIED` ledger rows cite evidence that is not a runnable command
(elided argument, unexpanded placeholder, inline scan, or no invocation at
all), and can `claims_check.py` name them without turning the standing gate red?

## Hypothesis

The four rows named in the task (C-3612, C-3613, C-3614, C-3711) are not
isolated: a mechanical rule finds them and more. If the count exceeds ~20, the
task's Stop applies: the rule ships as a report, opt-in as an error.

**Falsifier:** the rule does not name all four precheck rows, or it names a
row whose evidence is a complete command (C-3510's `pdata.py census …
--label A`) or plain prose with no backticked span (C-207, `switch 7…15`).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `docs/research/claims.md` |
| SHA-256 | `4d016ef5318a2e28ef7993435813b14adc81f434d2b7508742120ee41e77ad87` |
| Offset(s) / VA(s) | none (ledger rows) |
| Tool / version | `python3 3.13.18` |
| Repo tool | `tools/claims_check.py` (`evidence_reasons`, `bad_evidence`, `--strict-evidence`) |

## Method

1. **Sample and hash.** The ledger above, 2,367 rows, 1,376 with a Status
   starting `VERIFIED`.
2. **Commands.**

   ```bash
   grep -n 'C-3612\|C-3613\|C-3614\|C-3711' docs/research/claims.md | grep -cE '…|\.\.\.|--image-start START|--module MODULE'
   python3 tools/claims_check.py --selftest
   python3 tools/claims_check.py | grep -c '^  NONRUN'
   python3 tools/claims_check.py | grep -c 'NONRUN .*ellipsis'
   python3 tools/claims_check.py | grep -c 'NONRUN .*placeholder'
   python3 tools/claims_check.py | grep -c 'NONRUN .*inline'
   python3 tools/claims_check.py | grep -c 'NONRUN .*no-invocation'
   python3 tools/claims_check.py | grep -E 'NONRUN (C-3612|C-3613|C-3614|C-3711) '
   python3 tools/claims_check.py | grep -cE 'NONRUN (C-207|C-3510) '
   python3 tools/claims_check.py; echo "exit $?"
   python3 tools/claims_check.py --strict; echo "exit $?"
   python3 tools/claims_check.py --strict-evidence; echo "exit $?"
   ```

   The rule, per `VERIFIED` row, over the backticked spans after the first
   `EXP-…` name (the whole cell if none): an *invocation* span opens with
   `python3`, `tools/`, `git`, `curl`, `sha256sum`, `grep`, `cmp` or `stat`.
   `ellipsis`: an invocation span contains `...`/`…` once hash abbreviations
   (`[0-9a-f]{4,}…[0-9a-f]*`) are removed. `placeholder`: an invocation span
   contains `START`, `MODULE`, `VA` or a `<name>` token. `inline`: a span with
   `<<` or `python3 -c` and no `tools/` path. `no-invocation`: the cell has
   backticked spans and none is an invocation. A cell with no span is prose
   and not judged.
3. **Controls.** *Positive*: the four precheck rows must be named, and the
   `--selftest` rows `cmp ...` (C-3711 shape), `--image-start START --module
   MODULE` (C-3612 shape), prose-with-spans (C-3614 shape) and a bare
   `python3 -c` must fail. *Negative*: C-3510 (complete `pdata.py census`
   command), C-207 (prose `…`, no span), a `sha256sum` row quoting
   `92aa525d…`, and a non-`VERIFIED` row with `cmp ...` must stay clean.
4. **Scope.** 1,376 `VERIFIED` rows; 630 of them carry no backticked span
   after the EXP name (e.g. `§Observations, first block`) and are outside
   this rule — the "producer command omitted" case (C-3712) stays a
   reviewer's job. Non-`VERIFIED` rows are not judged.
5. **Falsifier.** As stated above, before the result.

## Observations

- Precheck `grep … | grep -cE …` prints `3` (C-3612, C-3613, C-3711);
  C-3614's cell is `census loop over \`pdata.load_table\`, \`meta["compressed"]\``.
- `--selftest`: `claims_check selftest: OK (47 checks)`.
- Non-runnable `VERIFIED` rows: **347** — `ellipsis` 31, `placeholder` 19,
  `inline` 3, `no-invocation` 294 (a row has one reason in this corpus; the
  sum is 347).
- The four precheck rows print as `NONRUN C-3711 ellipsis`,
  `NONRUN C-3612 placeholder`, `NONRUN C-3613 placeholder`,
  `NONRUN C-3614 no-invocation`.
- C-207 and C-3510 are not named (`grep -cE` prints `0`).
- Exit codes: default `0` (`claims_check: OK`, line
  `non-runnable evidence rows: 347 (warning; --strict-evidence fails)`);
  `--strict` `0`; `--strict-evidence` `1` (`claims_check: FAILED`).
- `inline` rows: C-3742, C-3610, C-4013. Typical `no-invocation` cells:
  `cerom.py exports commondll.dll` (C-780, no `python3 tools/` prefix),
  `sh4dis 0x3f8a0c` (C-2922), `fdisk -l`, `7z l` (C-002).

## Interpretation

- **FACT:** the rule names all four rows the task listed and none of the
  negative controls; the falsifier did not fire.
- **FACT:** 347 rows is far past the Stop bound of ~20 IDs, and
  `tools/gate.py` runs `claims_check.py --strict`, so making `--strict` fail
  on this rule would turn the gate red for every agent. Per the Stop, the rule
  ships as a report (default and `--strict`: warning, exit unchanged) with an
  opt-in error flag `--strict-evidence`.
- **OBSERVED:** 294 of the 347 are `no-invocation`, mostly shorthand
  (`cerom.py …`, `sh4dis …`) that a reader can resolve to `python3 tools/…`;
  the 53 `ellipsis`/`placeholder`/`inline` rows are the ones that cannot be
  re-run as written at all.
- **HYPOTHESIS:** a ratchet (a frozen list of the 347 legacy IDs, every new
  row must pass under `--strict`) would hold the line without a mass edit;
  it was not shipped because rows merging in parallel would turn `main`'s gate
  red between a ledger merge and the next rebase.

## Conclusion

`tools/claims_check.py` gains `bad_evidence()` and prints
`non-runnable evidence rows: N` plus one `NONRUN <id> <reasons>` line per row
on every run; `--json` carries `nonrunnable_evidence`; `--strict-evidence`
makes the rule exit 1. The default run and `--strict` (the gate) are
unchanged in verdict. Enforcement in `--strict` is handed on (H53 owns the
board `--strict`; H66 extends this parser): it needs either the 53 hard rows
fixed by the tasks that own them, or a ratchet. H61 (the cited EXP name must
exist) reuses `--strict-evidence` as its error switch.

## Reproduction

```bash
python3 tools/claims_check.py | grep -c '^  NONRUN'              # expected: 347 (at 934d76e)
python3 tools/claims_check.py --strict-evidence; echo "exit $?"  # expected: exit 1
```

## Follow-ups

- [ ] H53/H66: make the evidence rule an error under `--strict` once the 53
      `ellipsis`/`placeholder`/`inline` rows are fixed or a legacy ratchet lands.
