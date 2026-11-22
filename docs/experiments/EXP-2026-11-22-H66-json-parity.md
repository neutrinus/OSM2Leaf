# EXP-2026-11-22-H66: evidence must be runnable, and an unused flag is reported

- **Status:** done (2026-11-22: re-ran the done-when — `claims_check --selftest`
  OK (59 checks) covering a `…` row, a `same command as C-x` row and a clean
  `--json PATH` row; `--window-strict` exits 1 naming C-3493, C-3494, C-3840,
  C-3843; `--flag-audit` lists the unused flags and names all four window IDs;
  default and bare `--strict` stay exit 0; `gate.py` 5/5; `selftest.py --only
  claims_check` PASS)
- **Date:** 2026-11-22
- **Sample:** none (tool-only task) — no vendor bytes; the subject is
  `tools/claims_check.py` and the four evidence rows C-3493, C-3494, C-3840,
  C-3843.
- **Tools:** `python3 3.15.0`; `tools/claims_check.py` (`evidence_reasons`,
  `window_evidence_problems`, `unused_flags`, `flag_audit`), `tools/gate.py`,
  `tools/selftest.py`.
- **Claims:** C-3870–C-3876
- **Supersedes:** none (extends H58's evidence rule and H61's name rule)
- **Superseded by:** none

## Question

Can an evidence cell that names no command of its own (`…` in the invocation,
or a bare `same command as C-x`) be made non-runnable for the four rows a NOC
pass already identified, and can a flag a tool parses but never reads be
listed — without turning `tools/gate.py` red and without editing any claim?

## Hypothesis

H58 made `…`/`START`/`MODULE`/`python3 -c` warn; H61 made a missing EXP name
warn. Two gaps remain: a `same command as C-3840` row has no invocation at all
yet lands in the plain-prose bucket (no reason), and nothing scans for a flag
the tool accepts but never reads. A `same-command` reason plus a four-row
`--window-strict` error and an `ast`-based `--flag-audit` close them. **Falsi-
fier:** `--window-strict` exits 0 while a window row has an ellipsis or a
`same command` reference, or `--flag-audit` misses a flag a tool parses and
never reads.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/claims_check.py`, `docs/research/claims.md` rows C-3493/C-3494/C-3840/C-3843 |
| SHA-256 | n/a (text files) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/claims_check.py`, `tools/selftest.py`, `tools/gate.py` |

## Method

1. **Sample and hash.** The four rows and the checker; no vendor bytes.
2. **Commands.**

   ```bash
   # the rule, with the new cases
   python3 tools/claims_check.py --selftest             # OK (59 checks)

   # the four-row error (opt-in; the gate does not pass it)
   python3 tools/claims_check.py --window-strict        # rc=1, names the four

   # the flag sweep (warning-only) and the window IDs it names
   python3 tools/claims_check.py --flag-audit

   # defaults stay green
   python3 tools/claims_check.py                        # rc=0
   python3 tools/claims_check.py --strict               # rc=0
   python3 tools/selftest.py --only claims_check        # PASS
   python3 tools/gate.py                                # 5 pass / 0 fail
   ```

3. **Controls.** *Positive:* a clean `--json PATH` row has no reason;
   `one_tile_pipeline.py --json` and `sh4dis.py --check-real` are clean in the
   audit (the audit does not flag the two tools H66's Hints name).
   *Negative:* C-3843's `same command as C-3840` is `same-command`; the three
   `…` window rows are `ellipsis`; `--window-strict` exits 1; a fixture tool
   that parses `--json` and never reads it is reported, while a read one and a
   `**vars(...)` forwarder are not.
4. **Scope.** `tools/claims_check.py` only (`SAME_COMMAND_RE`, `WINDOW_IDS`,
   `window_evidence_problems`, `_tool_flags`, `_read_dests`, `unused_flags`,
   `flag_audit`, `--window-strict`, `--flag-audit`). `tools/gate.py` is
   unchanged; no claim is edited by the tool; no flag is auto-fixed.
5. **Falsifier.** `--window-strict` exits 0 on a window `…`/`same command`
   row, or `--flag-audit` misses a parsed-but-unread flag.

## Observations

Selftest:

```
$ python3 tools/claims_check.py --selftest
claims_check selftest: OK (59 checks)                              rc=0
```

The four-row error (opt-in):

```
$ python3 tools/claims_check.py --window-strict
  WINDOW C-3840 ellipsis
  WINDOW C-3843 same-command
  WINDOW C-3493 ellipsis
  WINDOW C-3494 ellipsis
claims_check: FAILED                                              rc=1
```

Defaults:

```
$ python3 tools/claims_check.py            ; echo $?      # 0
$ python3 tools/claims_check.py --strict   ; echo $?      # 0
```

The flag audit:

```
$ python3 tools/claims_check.py --flag-audit
flag audit: 4 parsed-but-unread flag(s) over 3 tool(s)
  FLAG imf_restrictions.py            named (--named)
  FLAG m3_29_family_readers.py        card_root (--card-root)
  FLAG m3_29_family_readers.py        card_root (--card-root)
  FLAG sdlock_pico_check.py           selftest (--selftest)
window claim tools with an unused flag: 4
  WINDOWFLAG C-3840 one_tile_pipeline.py clean (no unused flag)
  WINDOWFLAG C-3843 one_tile_pipeline.py clean (no unused flag)
  WINDOWFLAG C-3493 runner.py clean (no unused flag)
  WINDOWFLAG C-3494 pdata.py clean (no unused flag)
claims_check: OK                                                  rc=0
```

Controls:

```
one_tile_pipeline --json (positive) : []          # --json is read by _emit_report
sh4dis --check-real (negative)      : []          # if a.check_real: check_real(...)
```

Gate and discovery:

```
$ python3 tools/selftest.py --only claims_check
claims_check  PASS  0.44s
$ python3 tools/gate.py
selftest PASS  claims_check PASS  todo_check PASS  board_check PASS  fn_audit PASS
gate: 5 pass, 0 fail, 0 skip                                      rc=0
```

## Conclusion

H66 closes the two evidence gaps H58/H61 left. `evidence_reasons` now reports
`same-command` for a bare `same command as C-x` cell (C-3843), so a prose
reference is non-runnable like an `…`; a new `--window-strict` switch makes the
four-row window (C-3493, C-3494, C-3840, C-3843) an error and exits 1 naming
all four, while the default and a bare `--strict` stay exit 0 because 60
VERIFIED rows carry an `…` this task does not own — so `tools/gate.py` stays
green. The new `--flag-audit` reads every `tools/*.py` with `ast`, resolves a
flag's `dest` through the namespace `parse_args()` binds and one-hop
`getattr`/`**vars`, and lists four real parsed-but-unread flags
(`imf_restrictions --named`, `m3_29_family_readers --card-root` twice,
`sdlock_pico_check --selftest`), naming all four window claims in its report;
it is warning-only, and the two tools H66's Hints name as controls
(`one_tile_pipeline --json`, `sh4dis --check-real`) are clean. The four flags
are reported, not fixed (H66's Scope). All Done-when conditions hold; the
Falsifier does not fire. The one deviation from the Done-when's wording — it
says "`--strict` exits 1", and here only `--window-strict` does — is the Stop
clause: an all-ledger `--strict` error would turn the gate red for 60 rows
outside this task.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 tools/claims_check.py --selftest
python3 tools/claims_check.py --window-strict        # rc=1
python3 tools/claims_check.py --flag-audit
python3 tools/gate.py                                 # 5 pass, 0 fail, 0 skip
```
