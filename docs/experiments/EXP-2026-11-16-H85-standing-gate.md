# EXP-2026-11-16-H85: One standing gate with one PASS/FAIL/SKIP policy

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (tool-only task)` — the gate is proved with stub commands and
  the repo's own four tools; no vendor bytes are read by the selftest.
- **Tools:** python3 3.11, 3.13, 3.15 (all three parse and pass the selftest);
  repo tools `tools/gate.py` (new), `tools/selftest.py`, `tools/claims_check.py`,
  `tools/todo_check.py`, `tools/fn_audit.py`
- **Claims:** C-4080–C-4089
- **Supersedes:** none
- **Superseded by:** none

## Question

The TL/QA gate is four commands with four exit semantics. Can one runner apply
one policy — PASS / FAIL / SKIP-for-a-missing-vendor-input — and exit non-zero
iff a *runnable* gate failed, so the cycle-8 escape (an l3 suite that
`skip_unless`-skipped on a missing image while both agents read `passed=89/90`
as green) cannot recur silently?

## Hypothesis

The four tools already carry the information, but no shared policy: each exit
code means something different, and a missing vendor image reads as an
`SKIP` inside `selftest.py` while it is an exit `2` from `fn_audit.py`.
**Falsifier:** if classifying exit `2` needs a per-tool rule the runner cannot
derive from the tool's own message, or if a SKIP is indistinguishable from a
pass in the summary, the single-policy claim is false.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (tool-only task)`; the optional `archive/head256.img` |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | — |
| Tool / version | python3 3.11 / 3.13 / 3.15 |
| Repo tool | `tools/gate.py` |

## Method

1. **Sample.** The repo's own gate commands on this host, plus four stub
   programs the selftest writes (`exit 0`, `exit 1`, `exit 2 + a missing-input
   message`, `exit 2 + a malformed-input message`).
2. **Commands.**
   ```bash
   python3 tools/gate.py --selftest        # PASS/FAIL/SKIP with stubs
   python3 tools/gate.py                   # no image: fn_audit SKIP, exit 0
   ln -s …/archive/head256.img archive/head256.img
   python3 tools/gate.py                   # image: 4 PASS, exit 0
   python3 tools/gate.py --json -          # stdout is one JSON document
   python3 tools/gate.py --board-clean --no-count   # todo_check --strict: FAIL until H53
   ```
3. **Controls.** *Positive*: with the image all four gates `PASS` and the
   runner exits 0. *Negative*: a stub that exits 1 (or a repo `todo_check`
   with a block's `Status:` removed) makes the runner exit 1 and the row read
   `FAIL`; a stub that exits 2 **without** a missing-input marker is `FAIL`,
   not `SKIP` (so `fn_audit`'s exit 2 is not blanket-forgiven).
4. **Scope.** New `tools/gate.py`; `.github/workflows/ci.yml` (three gate
   steps collapse into one standing-gate step and its job summary);
   `AGENTS.md` (the commands list names `tools/gate.py` and states the policy).
   No tool's own rules change.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Selftest, on 3.11, 3.13 and 3.15 (`gate selftest: OK (11 checks, 0 failed)`):

```
ok   exit 0 -> PASS
ok   exit 1 -> FAIL
ok   exit 2 + missing-input message -> SKIP (not PASS)
ok   exit 2 + no missing-input marker -> FAIL
ok   exit 2 + 'cannot verify' (not a missing-input marker) -> FAIL
ok   declared-missing vendor input -> SKIP before running
ok   PASS + SKIP counts as a pass (exit 0 policy)
ok   any FAIL makes the run fail
ok   summary names the SKIP and its reason
ok   --json writes the same counts and is valid JSON
ok   --json never records a SKIP as PASS
```

No image:

```
GATE          RESULT    SECS  NOTE
selftest      PASS     49.58
claims_check  PASS      3.89
todo_check    PASS      0.04
fn_audit      SKIP      0.00  missing archive/head256.img
gate: 3 pass, 0 fail, 1 skip -- not covered: fn_audit (missing archive/head256.img)
```

With the image: `gate: 4 pass, 0 fail, 0 skip`.

A missing `Status:` line in a block (`todo_check` error) gives
`todo_check FAIL exit 1` and `gate: 1 pass, 2 fail, 1 skip`, runner exit 1;
`--board-clean` reports `todo_check FAIL exit 1` (H53's 66 strict errors) and
the runner exits 1, which is honest until the board is clean.

`selftest.py` discovers `tools/gate.py` (`tool:gate PASS`) and stays green:
`passed=90 failed=0 skipped=24 total=114`.

The SKIP markers are deliberately narrow (`no such file or directory:
'archive/`, `no image at `, `missing archive/`); a broad phrase like `cannot
verify` is a **FAIL**, so a real "cannot verify the snapshot" error cannot
masquerade as a SKIP. The selftest pins that case.

The CI step captures `gate.py`'s own exit code, not `tee`'s:
`rc=${PIPESTATUS[0]}` after the `… | tee gate.txt` pipe (reviewer round 1
caught `rc=$?` reading `tee`'s 0 and letting a FAILing gate pass CI).

## Interpretation

- **FACT:** the runner derives SKIP from a gate's own message, not from a
  per-tool table: exit `2` **and** a missing-input marker is SKIP, exit `2`
  without it is FAIL. The selftest pins both halves, so a future `fn_audit`
  that returns 2 for a bad snapshot cannot be mistaken for "no image".
- **FACT:** the summary prints `n pass, n fail, n skip` and names each SKIP
  with its reason; a SKIP-only difference never turns the run green when a
  runnable gate failed, and a SKIP alone exits 0 (the `realcheck.py`
  contract).
- **OBSERVED:** with H78 merged, `claims_check --strict --count-check` is
  green, so the standing gate is `4 PASS` with the image — the H85 Done-when's
  "claims_check FAIL until H78" parenthetical is already past.
- **LIMITATION:** this is a *standing* gate, not a per-task oracle; the TL
  still runs each task's `Done when` by hand. That is stated in the tool's
  docstring.

## Conclusion

`tools/gate.py` is the one standing gate: four commands, one fixed order, one
`PASS/FAIL/SKIP (reason)` table, one `--json` document, and an exit code that
distinguishes "a runnable gate failed" from "a vendor input was missing". CI
runs it; `--selftest` proves the policy with stubs, not with a live suite.

## Reproduction

```bash
python3 tools/gate.py --selftest
# gate selftest: OK (11 checks, 0 failed)
python3 tools/gate.py            # no image -> fn_audit SKIP, exit 0
python3 tools/gate.py --json -   # the same as valid JSON on stdout
python3 tools/selftest.py        # tool:gate PASS; passed=90 failed=0 skipped=24
```
