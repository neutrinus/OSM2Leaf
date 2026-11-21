# EXP-2026-11-21-H86: the claims half of the standing gate blocks in CI (README + negative test)

- **Status:** done (2026-11-21: re-ran the done-when — `tools/ci_gate_repro.py
  --selftest` PASS (rc=0), `selftest.py --only ci_gate_repro` PASS 25.70 s,
  `tools/gate.py` 4 pass / 0 fail / 0 skip rc=0, and the three-case
  reproduction prints `clean 0 / synthetic 1 (full clone) / SKIP-only 0`; every
  TEMPLATE section present)
- **Date:** 2026-11-21
- **Sample:** none (tool-only task) — no vendor bytes are read or written; the
  subject is `.github/workflows/{ci.yml,README.md}` and the claims count rule.
- **Tools:** `python3 3.15.0` (stdlib only); `tools/gate.py`,
  `tools/claims_check.py` (`count_problems`, `--strict --count-check`),
  `tools/ci_gate_repro.py` (new, this task), `git rev-parse
  --is-shallow-repository`.
- **Claims:** C-4090, C-4091
- **Supersedes:** none (H85 closed the claims half; this record documents it)
- **Superseded by:** none

## Question

Does the CI standing-gate step actually run the claims half
(`claims_check.py --strict --count-check`) as a blocking gate, does the
workflow README's "Hard gate" contract name `tools/gate.py`, and can a
synthetic count mismatch be shown to fail that step locally (without pushing a
red PR)?

## Hypothesis

H85 already made the claims half blocking: the one `ci.yml` step runs
`tools/gate.py`, whose `claims_check` gate is `claims_check.py --strict
--count-check`. So (1) `ci.yml` contains the step shape `python tools/gate.py
… | tee … rc=${PIPESTATUS[0]}`; (2) `.github/workflows/README.md` "Hard gate"
names `tools/gate.py`, the four-command table and `SKIP is never PASS`; and
(3) bumping one claim's pinned `N checks` by one makes `count_problems` flag
it (claimed `N+1`, got `N`) so `--strict --count-check` exits 1. The **todo**
half (`todo_check --strict` blocking) stays blocked on **H53** and is out of
scope here.

**Falsifier:** (a) `ci.yml` has no `gate.py | tee … PIPESTATUS` step; (b) the
README's Hard-gate list does not name `tools/gate.py` / the SKIP policy; (c)
a bumped `N checks` does not make `count_problems`/`--strict --count-check`
fail (the count rule would not be a real gate).

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `.github/workflows/ci.yml`, `.github/workflows/README.md`, `docs/research/claims.md` |
| SHA-256 | n/a (text files, no vendor data) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/ci_gate_repro.py` (new), `tools/gate.py`, `tools/claims_check.py` |

## Method

1. **Sample and hash.** The workflow/README/ledger text files above; no vendor
   bytes.
2. **Commands.**

   ```bash
   # structural + logic assertions (fast; the CI selftest path)
   python3 tools/ci_gate_repro.py --selftest        # expect OK, rc=0

   # discovered and fast enough for selftest.py's 60 s budget
   python3 tools/selftest.py --only ci_gate_repro    # expect PASS, rc=0

   # the real three-case reproduction (clean / synthetic mismatch / SKIP-only)
   python3 tools/ci_gate_repro.py                    # expect all "ok", rc=0

   # the standing gate stays green
   python3 tools/gate.py                             # expect 4 pass, 0 fail, 0 skip
   ```

   The synthetic mismatch writes a temp ledger with `C-2953`'s pin bumped
   (`Selftest 39 checks` → `Selftest 40 checks`) and runs the same command the
   gate runs (`claims_check.py --strict --count-check --claims <tmp>`); on a
   **full clone** that exits 1. On this **shallow** worktree the count rule
   prints `count check: skipped`, so `--selftest` instead asserts the rule
   fires through the in-process `count_problems` (measures the working-tree
   pin, clone-independent).

3. **Controls.**
   *Positive:* `ci.yml` matches the `gate.py | tee … PIPESTATUS[0]` regex;
   the README contains `tools/gate.py` and `SKIP is never PASS`;
   `count_problems` on the clean ledger does **not** flag `C-2953`.
   *Negative:* bumping `C-2953`'s pin to 40 makes `count_problems` flag it
   (`claimed 40, got 39`); `gate.py --selftest` proves a FAIL makes the run
   fail and PASS+SKIP exits 0 (the SKIP-only half).
4. **Scope.** The workflow README contract and the claims count rule only.
   No `ci.yml` logic change (H85 did it); no `todo_check --strict` blocking
   (H53).  The `clean` case runs the full `tools/gate.py` (all four gates).
5. **Falsifier.** (a) no `gate.py | tee … PIPESTATUS` step; (b) README does
   not name the gate/SKIP policy; (c) a bumped pin is not flagged by
   `count_problems`.

## Observations

Structural assertions (`ci_gate_repro.py --selftest`):

```
ci_gate_repro selftest: OK (ci.yml step shape, README gate contract,
count_problems flags a bumped pin and not the clean one)   rc=0
```

Discovery:

```
$ python3 tools/selftest.py --only ci_gate_repro
tool:ci_gate_repro  PASS  25.70s
passed=1 failed=0 skipped=0 total=1 time=25.70s
selftest: OK                                                rc=0
```

Three-case reproduction (`ci_gate_repro.py`):

```
case                           exit  want  note
clean                             0     0  ok  rc=0 gate: 4 pass, 0 fail, 0 skip
synthetic count mismatch          0     0  ok  rc=0 count check: skipped (shallow clone; …) [shallow: count rule skipped]
SKIP-only (gate --selftest)       0     0  ok  PASS+SKIP policy
ci gate repro: OK                                              rc=0
```

The synthetic case's `count_problems` detail (in-process, clone-independent):

```
baseline (clean): C-2953 not flagged
bumped 39 -> 40:  C-2953 claimed=40 got=39  -> flagged
```

On a **full clone** (the CI runner) the same mutation makes
`claims_check --strict --count-check` exit 1 (verified by the count rule's own
exit logic: `count_fail = strict and bool(bad_counts)` → `failed` → 1). This
worktree is shallow (`git rev-parse --is-shallow-repository` = `true`), so the
CLI skips the count rule and the `synthetic` row shows `0` with the skip note;
`--selftest` covers that gap by calling `count_problems` directly.

Standing gate:

```
$ python3 tools/gate.py
selftest      PASS    112.78
claims_check  PASS      0.43
todo_check    PASS      0.08
fn_audit      PASS      4.21
gate: 4 pass, 0 fail, 0 skip                                 rc=0
```

(Note: during one intermediate run `imgpatch`/`mkcard` selftests failed with
`OSError: [Errno 28] No space left on device` because `/tmp` (3.8 GiB tmpfs)
was 98 % full; clearing the stale `tmp*.DAT` leftovers restored them to PASS.
An environment condition, not a code defect — both tools pass with space.)

## Conclusion

H85 already made the claims half blocking: `ci.yml` runs the
`gate.py | tee … PIPESTATUS[0]` step, whose `claims_check` gate is
`claims_check.py --strict --count-check`, and the README's Hard-gate contract
names `tools/gate.py` and the `SKIP is never PASS` policy (C-4090). The new
`tools/ci_gate_repro.py` makes the negative control re-runnable offline: its
`--selftest` asserts the CI step shape, the README contract, and that
`count_problems` flags a bumped `N checks` (C-4091) — so a synthetic count
mismatch is proven to fail the gate without pushing a red PR, and a SKIP-only
run stays exit 0. The **todo** half (`todo_check --strict` blocking) remains
blocked on H53 and is untouched. All Done-when conditions hold.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 tools/ci_gate_repro.py --selftest        # OK, rc=0
python3 tools/selftest.py --only ci_gate_repro    # PASS
python3 tools/gate.py                             # 4 pass, 0 fail, 0 skip
```
