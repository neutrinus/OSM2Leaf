# EXP-20261116-H74: `claims_check` count and evidence-path detector

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (tool-only task)` — the subject is the ledger checker and two
  selftest footers; the real ledger is read from the checkout, no vendor bytes
  are examined. The tool runs are reproduced from `origin/main` (`0650616`).
- **Tools:** `python3 3.15.0` (stdlib only, no zlib claims), repo tools
  `tools/claims_check.py`, `tools/fn_match.py`, `tools/fn_audit.py`,
  `git` (`git archive <rev> tools` to replay a tool at a past commit),
  `tar`.
- **Claims:** C-3950–C-3959
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `claims_check` reject a claim that cites a selftest count its own evidence
command never prints, and an evidence path that does not exist, without needing
a vendor image and without turning the default run red?

## Hypothesis

A selftest count is mechanical: the cited `tools/X.py --selftest` prints a
footer with the number of checks it ran, so a claim's `N checks`/`N/N` can be
compared to the number at *the revision the claim names* (the EXP record's last
commit), not at `main`. A backticked `archive/…`/`docs/…` path after a `;` in
the evidence cell either resolves or it does not.

**Falsifier:** the positive controls C-3704 (`26 checks`) and C-3934
(`58 checks`) fail the new rule on `main`, or the default run stops exiting 0
on the real ledger, or the fixtures (disagree / missing path) do *not* fail
under `--strict`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none (tool-only task) |
| SHA-256 | n/a |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0`; `git`, `tar` |
| Repo tool | `tools/claims_check.py` (the one that produced every number below) |

## Method

1. **Sample and hash.** No vendor sample. The corpus is `docs/research/claims.md`
   at `origin/main` `0650616`; the tools are replayed from commits
   `334f092` (`fn_match`), `7af443f` (`fn_audit`), `4de2f97` (`cerom`) via
   `git archive`.

2. **Commands.** Runnable as written from the repository root:

   ```bash
   python3 tools/claims_check.py --selftest          # 14 checks, exit 0
   python3 tools/claims_check.py                     # default: exit 0
   python3 tools/claims_check.py --count-check       # 0 mismatches, exit 0
   python3 tools/claims_check.py --strict; echo $?   # 1 (missing paths)
   python3 tools/claims_check.py --strict --count-check 2>&1 \
       | grep 'MISSING C-3703'                        # archive/us256.img
   python3 tools/fn_match.py --selftest | tail -1     # 29 checks, 0 failed
   python3 tools/fn_audit.py --selftest | tail -1     # 70 checks, 0 failed
   # the historical counts the ledger pins (git archive, no vendor data):
   d=$(mktemp -d); git archive 334f092 tools | tar -x -C "$d"
   PYTHONPATH="$d/tools" python3 "$d/tools/fn_match.py" --selftest | tail -1
   d=$(mktemp -d); git archive 7af443f tools | tar -x -C "$d"
   PYTHONPATH="$d/tools" python3 "$d/tools/fn_audit.py" --selftest | tail -1
   ```

3. **Controls.**
   *Positive*: C-3704 (`26 checks`, `fn_match`) and C-3934 (`58 checks`,
     `fn_audit`) are true on `main` and must stay green; default
     `claims_check.py` exits 0 on the real ledger.
   *Negative*: the `--selftest` fixtures (a claim pinning 22 against a 26-check
     command fails; the same shape with 26 passes; a missing `archive/…` path
     after a `;` is named; a placeholder/`;`-less path is skipped).

4. **Scope.** Every claim row in `docs/research/claims.md` at `0650616`:
   16 rows pin a check count and cite a measurable selftest; 56 rows carry a
   backticked `archive/`/`docs/` path after a `;`. Excluded: prose in EXPs (an
   EXP line is not a claim row; H75 repairs the M1.27 EXP), tools whose
   selftest prints neither a footer count nor `ok` lines (skipped, never
   scored 0), and any reader/firmware command (needs an image). The path count
   depends on which git-ignored `archive/` files the checkout has (see
   Observations).

5. **Falsifier.** As stated in Hypothesis.

## Observations

Default run at `0650616` (59 hits in this worktree; 6 in the reference
checkout, which has the pinned `archive/head256.img` — see Interpretation):

```
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
missing evidence paths: 59
count check: off (--count-check)
claims_check: OK                 (exit 0)
```

`--count-check` (16 count-bearing rows, every tool replayed at its EXP's last
commit):

```
count mismatches: 0
claims_check: OK                 (exit 0)
```

Historical counts, replayed:

| Claim | Pinned | Revision | Printed |
| --- | --- | --- | --- |
| C-3704 | 26 | `334f092` (M1.27 EXP head) | 26 |
| C-3934 | 58 | `7af443f` (H72 EXP head) | 58 |
| C-568 | 46 | `4de2f97` (EXP-2026-11-05-47) | 46 |
| C-570 / C-650 | 186 / 391 | respective EXP heads | 186 / 391 |
| C-2085 / C-960 / C-1060 | 44 / 15 / 48 | respective EXP heads | match |
| C-1090 / C-1994 / C-2577 | 68 / 18 / 25 | respective EXP heads | match |
| C-3713 / C-3690 / C-3894 / C-2733 | 20 / 14 / 14 / 9 | respective EXP heads | match |

Working tree footers after the H74 change: `fn_match selftest: OK (29 checks, 0
failed)`, `selftest: OK (70 checks, 0 failed)`.

The negative fixture that pins the M1.27 EXP's number against the same tool
prints, unchanged:

```
C-9002 claimed 22, tools/fn_match.py prints 26 (334f092)
```

`--strict` on the real ledger: on the reference checkout (pinned
`archive/head256.img` present) `missing evidence paths: 6` over 6 rows, exit 1,
naming `C-3703 archive/us256.img` (as the block requires), C-3701/3702/3705
(the same US head), `C-500 archive/images/SHA256SUMS` and
`C-630 archive/images/LEAF_…eu.img`; in a fresh worktree without the
git-ignored `archive/head256.img` the same rule reports 59 hits over 56 rows,
adding every `archive/head256.img` row. `--count-check` adds 0 mismatches to
that exit.

Fixture status: disagree → fails, agree → passes, missing path → named,
placeholder/`;`-less → skipped, all in `--selftest` (14 checks, exit 0). The
revision fixture also runs the real `fn_match.py` at `334f092` (26) when that
commit is present, so the M1.27 `22` is checked against the tool itself, not
only against a stub.

## Interpretation

- **FACT:** The count rule is mechanical and green on the real ledger: every
  count-bearing row matches the tool at the revision its EXP names, including
  the two required positive controls C-3704 (`26`) and C-3934 (`58`).
- **FACT:** The M1.27 EXP's `22` is a genuine mismatch at `334f092` (which
  prints 26), reproduced by the fixture. It is prose in an EXP, not a claim
  row, so H74's mechanical rule does not (and must not silently) rewrite it;
  H75 owns that repair.
- **OBSERVED:** C-568 pins `46` while `main` prints `411`; replayed at its own
  EXP commit (`4de2f97`) it is `46`, so "compare at the revision the text
  names" is the correct reading of the block's stop clause, not a loophole:
  pinning a moving count at a past merge is checkable with `git archive`.
- **OBSERVED:** `--strict` is red only on archive data this checkout lacks
  (`archive/` is git-ignored); in a fresh worktree even `archive/head256.img`
  is absent, so the hit count is machine-dependent (6 vs 59) while the
  named-row set only grows. The rule is correct by design and rule 11 makes
  those paths re-creatable, so H75/owners pin a fetch command, not a shipped
  file.
- **UNKNOWN:** none material; the count rule skips tools whose selftest prints
  neither a footer nor `ok` lines (none among the 16 measured rows).

## Conclusion

`tools/claims_check.py` gains `--strict` and `--count-check`: a claim's
`N checks`/`N/N` must equal what its cited `--selftest` prints at the revision
its EXP names, and every backticked `archive/…`/`docs/…` path after a `;` in the
evidence cell must exist. `tools/fn_match.py`/`tools/fn_audit.py` footers now
print the check count. Default stays exit 0 on the real ledger; `--strict`
exits 1 naming C-3703 and the other absent heads, which H75 repairs. Because
H58/H61 are still open, H74 also adds the path existence rule and the
`--strict` flag themselves, so the two rules ship together rather than waiting
on an unmerged parser.

## Reproduction

```bash
python3 tools/claims_check.py --selftest              # expected: 14 checks, exit 0
python3 tools/claims_check.py --count-check           # expected: 0 mismatches, exit 0
python3 tools/claims_check.py --strict; echo $?       # expected: names C-3703, exit 1
```

## Follow-ups

- [ ] H75: repair C-3703 (`archive/us256.img` path and the `--fixture` vs
      `match --va` histogram) and the M1.27 EXP's `22` → `26`, so H74's
      `--strict` can land green on that row-set.
- [ ] H58/H61 (still open): when their `bad_evidence`/EXP-name rules merge,
      fold them under the same `--strict` flag rather than a second parser.
- [ ] H62: a `US256` pinned fetch alias would let C-3701/3702/3703/3705 name a
      re-creatable path instead of an absent `archive/us256.img`.
