# EXP-20261116-H78: `--strict` must run the count rule, and a docs-only EXP edit must not re-pin a claim

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (tool-only task)` — the subject is `tools/claims_check.py`'s
  revision rule; the run replays committed tools with `git archive`. No vendor
  bytes are read.
- **Tools:** python3 3.15.0; repo tools `tools/claims_check.py`,
  `tools/fn_match.py`; `git archive`/`tar` for the historical replay.
- **Claims:** C-4010–C-4019
- **Supersedes:** none (corrects H74's `--strict` contract and H75's Result)
- **Superseded by:** none

## Question

Why does `python3 tools/claims_check.py --strict` exit 0 on `main` while the same
ledger fails its own count rule, and should a later docs-only edit to an EXP
change which tool revision its claims are measured against?

## Hypothesis

Two independent defects, both visible in the cycle-8 window: `--strict` never
runs `count_problems`, and `_exp_revision` returns the EXP file's **newest**
commit, so H75's required `Correction (H75)` section (a docs-only append) moved
C-3704's measurement from `334f092` (26 checks, the number the claim states) to
`ec58d12` (29). Falsifier: if `--strict` already ran the count rule, the
`--strict` exit would have been 1 on `main`; if the append did not matter, the
measured revision would still be `334f092` and `--count-check` would be 0.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (the ledger and the tool history) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | none |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (`count_problems`, `_exp_revision`, `main`) |

## Method

1. **Sample and hash.** The ledger at the branch base `8a2a48a` and the two EXPs
   named below; tool revisions replayed with `git archive <rev> tools`.
2. **Commands.** Runnable as written:

   ```bash
   python3 tools/claims_check.py --strict; echo $?                 # pre-fix: 0
   python3 tools/claims_check.py --strict --count-check; echo $?   # pre-fix: 1
   python3 tools/claims_check.py --count-check                     # pre-fix: 1 mismatch
   python3 tools/claims_check.py --selftest
   ```

   Historical counts (each printed by the tool at that revision):

   ```bash
   for rev in 92550d6 334f092 2709645 ec58d12; do
     d=$(mktemp -d); git archive "$rev" tools | tar -x -C "$d"
     PYTHONPATH="$d/tools" python3 "$d/tools/fn_match.py" --selftest | grep -c '^ok'
     rm -rf "$d"
   done
   # 22 (92550d6)  26 (334f092)  26 (2709645)  29 (ec58d12)
   ```

3. **Controls.** *Positive*: after the fix `--strict` exits 0 and
   `--count-check` prints `count mismatches: 0`. *Negative*: changing C-3704's
   `26` to `25` (or `27`) makes `--strict` exit 1 with a `COUNT` line, so the
   count rule is not disabled, only made visible to `--strict`.
4. **Scope.** `tools/claims_check.py` only: `_exp_revision`, `_run_counts`,
   `main`, the module docstring and the `--selftest` cases. No claim text, no
   EXP record, no other rule.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Pre-fix, on the branch base `8a2a48a` (cycle-8 `main`):

```
$ python3 tools/claims_check.py --strict; echo $?
0
$ python3 tools/claims_check.py --strict --count-check 2>&1 | grep -E 'COUNT|mismatches'
count mismatches: 1
  COUNT C-3704 claims 26, tools/fn_match.py prints 29 (ec58d12075bac822dbc0513dac98188d08b391d0)
$ python3 tools/claims_check.py --strict --count-check; echo $?
1
```

Bisect of the window (the same `--count-check` at each merge):

```
4dce4dd  (M1.27 merged, EXP head 334f092)  count mismatches: 0
e0a8bf5  (#198,          EXP head 334f092)  count mismatches: 0
95f7964  (#199, H75,     EXP head ec58d12)  count mismatches: 1
caff825  (#200,          EXP head ec58d12)  count mismatches: 1
```

Post-fix, same tree:

```
$ python3 tools/claims_check.py --strict; echo $?
0
$ python3 tools/claims_check.py --count-check
count mismatches: 0
claim/EXP count conflicts: 0
$ python3 tools/claims_check.py --strict --count-check; echo $?
0
$ python3 tools/claims_check.py --selftest
claims_check selftest: OK (25 checks)
$ git config --get-regexp . >/dev/null; # healthy tree
$ python3 tools/todo_check.py        # OK
$ python3 tools/selftest.py          # passed=90 failed=0 skipped=23 (with the head)
```

`_exp_revision("EXP-2026-11-16-M1.27-fn-match-leaf")` now returns
`334f0922653565e8ec15901a0ed6e64735d5346e` (the EXP+tool commit), not
`ec58d12…` (the docs-only append).

Negative control: C-3704 `26` -> `25`:

```
count mismatches: 1
  COUNT C-3704 claims 25, tools/fn_match.py prints 26 (334f092…)
exit 1
```

## Interpretation

- **FACT:** `--strict` did not run the count rule; on `main` it exited 0 while
  `--strict --count-check` exited 1. H74's Result ("`--strict` (and
  `--strict --count-check`) exits 1 naming exactly the two genuine defects")
  still held at H74's merge, but the ledger's only red part was then unreachable
  from the standing gate.
- **FACT:** the measured revision moved to `ec58d12` because H75's
  `Correction (H75)` section is a docs-only commit; the M1.27 EXP's measurement
  revision was `334f092`, where the tool printed 26 — the number C-3704 states.
- **OBSERVED:** of the 19 rows that pin a count and cite a resolvable selftest
  (printed by the probe in Reproduction), the new rule changes three
  revisions: C-3704 `ec58d12 -> 334f092` (29 -> 26), C-3713
  `b5899ccb -> 322fd119` (count preserved) and C-3934 `7af443f0 -> 96ba9c02`
  (count preserved: `git archive … fn_audit.py --selftest | grep -c '^ok'`
  prints 58 at both). The other 16 keep their revision; 0 rows are skipped.
- **FACT (navigator round 1):** a record whose history never changed a tool had
  `_pinned_revision == None` and the old `count_problems` then measured the
  tool at the **working tree** (`rev=None`), contradicting the intended skip.
  Constructed with `EXP-2026-11-05-01-drstr-node-table` (a real record whose
  history never moved a tool): the synthetic row reported `rev: working tree`.
  `count_problems` now skips a row whose EXP record exists and has no
  measurement revision (no run, no verdict); a row naming a **nonexistent**
  record keeps the legacy working-tree measurement so H61's EXP-existence
  follow-up does not lose its signal. `--selftest` case (i) covers it.
- **UNKNOWN:** none material, and the skip path is **constructed only**: a
  probe over the real ledger prints `pinned rows 19 skipped(no rev) 0`, so the
  `None` branch has no live row today. The selftest case (i) and the probe in
  Reproduction are the whole evidence for it.

## Conclusion

`--strict` now runs the count rule, and the measurement revision is the newest
commit that changed the EXP *and* a tool, so appending a `Correction` section no
longer re-pins a claim against a tool version it never measured. `--strict` and
`--count-check` are both green on the real ledger, a one-digit change to C-3704
still fails, and the `--selftest` covers the append case with an injected git
history (25 checks).

## Reproduction

```bash
python3 tools/claims_check.py --strict; echo $?        # 0
python3 tools/claims_check.py --count-check            # count mismatches: 0
python3 tools/claims_check.py --selftest               # OK (25 checks)

# the ledger's pinned rows, and how many have no measurement revision
python3 - <<'EOF'
import sys; sys.path.insert(0, 'tools')
import claims_check as cc
rows = cc.parse_claim_rows(open('docs/research/claims.md').read())
n = skipped = 0
for cid, line in rows:
    t, ev = cc.claim_text(line), cc.evidence_cell(line)
    if cc.check_count_token(t) is None: continue
    if '--selftest' not in t and '--selftest' not in ev: continue
    if not cc.selftest_tools(ev): continue
    n += 1
    exps = cc.EXP_TOKEN_RE.findall(ev) or cc.EXP_TOKEN_RE.findall(t)
    skipped += cc._pinned_revision(ev, exps[0] if exps else '') is None
print('pinned rows', n, 'skipped(no rev)', skipped)   # 19 0
EOF

# the skip path, constructed on a real record whose history never moved a tool
python3 - <<'EOF'
import sys; sys.path.insert(0, 'tools')
import claims_check as cc
print(cc._exp_revision('EXP-2026-11-05-01-drstr-node-table'))   # None
row = ("| C-9999 | 26 checks. | VERIFIED (tool) | H | "
       "EXP-2026-11-05-01-drstr-node-table; `python3 tools/fn_match.py --selftest` |\n")
calls = []
print(cc.count_problems(cc.parse_claim_rows(row),
                        runner=lambda t, r=None: (calls.append((t, r)), (29, 0))[1]),
      calls)                                                  # [] []
EOF
```

## Follow-ups

- [ ] E3: H86 flips `--strict` into `ci.yml` as a blocking step (H78 is the rule
      half; H86 is the workflow half).
