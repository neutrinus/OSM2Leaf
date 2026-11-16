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
commit), not at `main`. A backticked `archive/…`/`docs/…` path is either
checked-in (must exist) or git-ignored vendor data (rule 11 makes it fetchable),
so only an unpinned vendor path or a claim/EXP disagreement is a defect.

**Falsifier:** the positive controls C-3704 (`26 checks`) and C-3934
(`58 checks`) fail the new rule on `main`, or the default run stops exiting 0
on the real ledger, or the fixtures (disagree / missing path) do *not* fail
under `--strict`, or `--strict` on a clean checkout names a legitimate vendor
reference.

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
   python3 tools/claims_check.py --selftest          # 20 checks, exit 0
   python3 tools/claims_check.py                     # default: exit 0
   python3 tools/claims_check.py --count-check       # 0 mismatches, exit 0
   python3 tools/claims_check.py --strict; echo $?   # 1
   python3 tools/claims_check.py --strict --count-check 2>&1 \
       | grep -E 'MISSING|CONFLICT'                  # C-3703 + C-3704
   python3 tools/fn_match.py --selftest | tail -1     # 29 checks, 0 failed
   python3 tools/fn_audit.py --selftest | tail -1     # 70 checks, 0 failed
   # the historical counts the ledger pins (git archive, no vendor data):
   d=$(mktemp -d); git archive 334f092 tools | tar -x -C "$d"
   PYTHONPATH="$d/tools" python3 "$d/tools/fn_match.py" --selftest | grep -c '^ok'
   d=$(mktemp -d); git archive 7af443f tools | tar -x -C "$d"
   PYTHONPATH="$d/tools" python3 "$d/tools/fn_audit.py" --selftest | grep -c '^ok'
   d=$(mktemp -d); git archive 4de2f97 tools | tar -x -C "$d"
   PYTHONPATH="$d/tools" python3 "$d/tools/cerom.py" --selftest | tail -1
   ```

3. **Controls.**
   *Positive*: C-3704 (`26 checks`, `fn_match`) and C-3934 (`58 checks`,
     `fn_audit`) are true at the revision their EXP names and must stay green;
     default `claims_check.py` exits 0 on the real ledger.
   *Negative*: the `--selftest` fixtures (a claim pinning 22 against a 26-check
     command fails; the same shape with 26 passes; a missing unpinned
     `archive/…` path after a `;` is named; a placeholder/`;`-less path is
     skipped; `archive/images/**`/`archive/sd-images/**` and a pinned head are
     exempt; a claim's count disagreeing with its EXP's count is a conflict).

4. **Scope.** Every claim row in `docs/research/claims.md` at `0650616`:
   **17 rows** pin a `N checks`/`N/N` token and cite a `--selftest` on a
   resolvable tool (16 excluding C-3954, the row that describes this selftest).
   At the revision each EXP names the rule reads a count for 13 of the 17; four
   print neither a footer count nor `^ok` lines there and are skipped, never
   scored 0 (C-553 `header_block.py` prints `37/37 passed`, C-2733/C-3894
   `selftest.py`, C-3954 `claims_check.py` at `3f73bfb` whose own strict
   assertion fails). Excluded: prose in EXPs (an EXP line is not a claim row;
   H75 repairs the M1.27 EXP), and any reader/firmware command (needs an
   image).

5. **Falsifier.** As stated in Hypothesis.

## Observations

Default run in a clean worktree (every `archive/` file git-ignored and absent):

```
duplicate claim IDs: 0
unregistered proposed claims: 0
bad annotations: 0
genuine missing evidence paths: 1
  MISSING C-3703 archive/us256.img
exempt vendor references: 58
count check: off (--count-check)
claim/EXP count conflicts: 1
claims_check: OK                 (exit 0)
```

`--count-check` adds `count mismatches: 0`; no `COUNT …` line is emitted:

```
count mismatches: 0
claims_check: OK                 (exit 0)
```

Historical counts, replayed (each line is the command output above):

```
26      # fn_match @ 334f092 (M1.27 EXP head)
58      # fn_audit @ 7af443f (H72 EXP head)
cerom selftest: 46 checks OK (synthetic ROM, no vendor data)   # @ 4de2f97
```

Working-tree footers after the H74 change:

```
fn_match selftest: OK (29 checks, 0 failed)
selftest: OK (70 checks, 0 failed)
```

The claim/EXP disagreement, emitted by `--strict` (the M1.27 EXP quotes 22 for
the tool that prints 26 at `334f092`):

```
CONFLICT C-3704 claims 26, tools/fn_match.py quotes 22 (EXP-2026-11-16-M1.27-fn-match-leaf)
```

The path rule classifies each backticked `archive/…`/`docs/…` path:
`tracked` (`docs/…`, must exist), `vendor-dir` (`archive/images/**`,
`archive/sd-images/**`), `vendor-pin` (`archive/head256.img`, fetched by
`fetch_image.py --image IMG256`; also any git-ignored path whose cell carries a
fetch command or a pinned SHA-256), `vendor-sibling` (a git-ignored path on a row
that also names a pinned head), and `gd` (an unpinned git-ignored path — the
only genuine defect). On the clean worktree the rule emits **1 genuine**
(`C-3703 archive/us256.img`) and **58 exempt**. The exempt count is
checkout-dependent (a branch without the H74 rows read 6 absent paths on the
reference checkout); that is exactly why the rule classifies the reference
instead of counting absent files: only C-3703's unpinned US head stays `gd`,
while C-3701/3702/3705 are `vendor-sibling` and C-500/C-630/C-2460 are
`vendor-dir`.

`--strict` therefore exits 1 naming exactly the two genuine defects, and
`--strict --count-check` keeps that result (`count mismatches: 0`):

```
genuine missing evidence paths: 1
  MISSING C-3703 archive/us256.img
count mismatches: 0
  CONFLICT C-3704 claims 26, tools/fn_match.py quotes 22 (EXP-2026-11-16-M1.27-fn-match-leaf)
claims_check: FAILED
```

Fixture status: disagree → fails, agree → passes, revision pin → named, path
classes (vendor-dir / vendor-pin / vendor-sibling / gd) → classified, claim-vs-EXP
conflict → named, all in `--selftest` (20 checks, exit 0). The revision fixture
also runs the real `fn_match.py` at `334f092` (26) when that commit is present,
so the M1.27 `22` is checked against the tool itself, not only against a stub.

## Interpretation

- **FACT:** The count rule is mechanical and green on the real ledger: every
  measurable row matches the tool at the revision its EXP names, including the
  two required positive controls C-3704 (`26`) and C-3934 (`58`).
- **FACT:** The M1.27 EXP's `22` is a genuine mismatch at `334f092` (which
  prints 26), reproduced by the fixture and surfaced as the `CONFLICT` line. It
  is prose in an EXP, not a claim row, so H74's rule does not (and must not
  silently) rewrite it; H75 owns that repair.
- **OBSERVED:** C-568 pins `46` while `main` prints `411`; replayed at its own
  EXP commit (`4de2f97`) it is `46`, so "compare at the revision the text
  names" is the correct reading of the block's stop clause, not a loophole:
  pinning a moving count at a past merge is checkable with `git archive`.
- **OBSERVED:** `--strict` is red only on two genuine defects: the unpinned
  `archive/us256.img` (C-3703, no H62 fetch) and the 26-vs-22 disagreement. All
  other absent paths are git-ignored vendor data (rule 11) in an exempt class,
  so the exit does not depend on which optional `archive/` files a checkout has.
- **UNKNOWN:** none material; the count rule skips four rows whose tool prints
  neither a footer nor `^ok` lines at the pinned revision, never scoring them 0.

## Conclusion

`tools/claims_check.py` gains `--strict` and `--count-check`: a claim's
`N checks`/`N/N` must equal what its cited `--selftest` prints at the revision
its EXP names, a claim and the EXP it cites must quote the same count, and
every backticked path must be either a checked-in file or classifiable vendor
data. `tools/fn_match.py`/`tools/fn_audit.py` footers now print the check
count. Default stays exit 0 on the real ledger; `--strict` exits 1 naming
exactly C-3703 and the C-3704 conflict, which H75 repairs. Because H58/H61 are
still open, H74 also adds the path existence rule and the `--strict` flag
themselves, so the two rules ship together rather than waiting on an unmerged
parser.

## Reproduction

```bash
python3 tools/claims_check.py --selftest              # expected: 20 checks, exit 0
python3 tools/claims_check.py                         # expected: exit 0
python3 tools/claims_check.py --count-check           # expected: 0 mismatches, exit 0
python3 tools/claims_check.py --strict; echo $?       # expected: C-3703 + C-3704, exit 1
```

## Follow-ups

- [ ] H75: repair C-3703 (`archive/us256.img` path and the `--fixture` vs
      `match --va` histogram) and the M1.27 EXP's `22` → `26`, so H74's
      `--strict` can land green on that row-set.
- [ ] H58/H61 (still open): when their `bad_evidence`/EXP-name rules merge,
      fold them under the same `--strict` flag rather than a second parser.
- [ ] H62: a `US256` pinned fetch alias would let C-3701/3702/3703/3705 name a
      re-creatable path instead of an absent `archive/us256.img`.
