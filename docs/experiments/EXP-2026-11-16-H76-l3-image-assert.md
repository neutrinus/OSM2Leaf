# EXP-20261116-H76: the l3 image suite pinned `0 moved`

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (tool-only task)` — the result is a test assertion in
  `tools/selftest.py`; the image-bearing check is a `skip_unless` suite that
  runs only where a head image exists.
- **Tools:** python3 3.13.1; `tools/selftest.py`, `tools/fn_audit.py`
- **Claims:** C-3990, C-3991, C-3992
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `test_fn_audit_scope_l3_image` accept the H69 moved-only outcome, or does
it pin the exact byte-stable string so that any line shift in `TODO.md` turns
the full suite red?

## Hypothesis

The assertion pins `CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved`. H69
established that a moved-only identity set is a `CORPUS DRIFT` warning with
**exit 0** (a line move is prose, not a corpus change), so a TODO edit that
moves l3 citation lines must leave the gate green and must not fail the test.
Falsifier: on a tree whose gate prints `CORPUS DRIFT: … 0 new / 0 gone / N
moved` and exits 0, the full suite fails at the literal string.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (EU 2011 head, git-ignored, fetched per rule 11) |
| SHA-256 | `92aa525d…007f9` (head-only; see `docs/research/sources.md`) |
| Offset(s) / VA(s) | none (test-level assertion) |
| Tool / version | python3 3.13.1 |
| Repo tool | `tools/selftest.py` (`test_fn_audit_scope_l3_image`), `tools/fn_audit.py` (`--corpus --overlay`) |

## Method

1. **Sample and hash.** No vendor bytes are read by the assertion under test
   beyond the l3 gate run it already performed; the sample is the committed
   docs base and l3 overlay snapshots.
2. **Commands.** Runnable as written:

```bash
# the gate on the current tree (H74's TODO edit moved l3 lines)
python3 tools/fn_audit.py archive/head256.img \
  --corpus docs/research/fn-audit-corpus-2026-11-16.json \
  --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json --quiet
# exact literal the old assertion demanded (must print 0)
python3 tools/fn_audit.py archive/head256.img \
  --corpus docs/research/fn-audit-corpus-2026-11-16.json \
  --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json --quiet \
  | grep -c "CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved"
# the suite
python3 tools/selftest.py --only fn_audit_l3_image
```

3. **Controls.** *Positive*: the suite passes when the gate prints
   `CORPUS (OK|DRIFT): L3 OVERLAY: 0 new / 0 gone / N moved` with exit 0.
   *Negative*: a temp overlay with one row deleted prints
   `CORPUS STALE: L3 OVERLAY: 1 new / 0 gone / N moved` and exits 1; the relaxed
   assertion must still reject it.
4. **Scope.** `tools/selftest.py` only: the `fn_audit_l3_image` builtin suite.
   `tools/fn_audit.py`'s H69 policy is out of scope and unchanged.
5. **Falsifier.** If the shipped assertion still matched an `OK`-only form or
   dropped the `CORPUS STALE` rejection, the one-row-deleted overlay would
   pass the assertion — the negative control would show it.

## Observations

Before (`main` at `4dce4dd`):

```
$ python3 tools/fn_audit.py … --quiet
CORPUS DRIFT: DOCS BASE: 0 new / 0 gone / 125 moved
CORPUS DRIFT: L3 OVERLAY: 0 new / 0 gone / 51 moved          # exit 0
$ … | grep -c "CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved"
0
$ python3 tools/selftest.py
fn_audit_l3_image              FAIL  AssertionError: fn_audit: DOCS BASE:
passed=89 failed=1 skipped=23 total=113
```

After (this commit):

```
$ python3 tools/selftest.py --only fn_audit_l3_image
passed=1 failed=0 skipped=0 total=1
$ python3 tools/selftest.py
passed=90 failed=0 skipped=23 total=113

# negative control: overlay with rows[0] deleted
gate exit= 1
  CORPUS STALE: L3 OVERLAY: 1 new / 0 gone / 55 moved
regex matched= False
STALE present= True
relaxed assertion would fail= True
```

## Interpretation

- **FACT:** the old assertion required the literal `0 moved`; on the H74 tree
  that string never appears (grep count 0) and the suite failed.
- **FACT:** H69's documented outcome for an unchanged identity set is either
  `CORPUS OK` or a `CORPUS DRIFT` warning, both exit 0.
- **OBSERVED:** relaxing to `CORPUS (OK|DRIFT): … \d+ moved` plus a
  `CORPUS STALE` rejection makes the suite pass on the drifted-but-equivalent
  tree and still fails a genuine row removal (exit 1, `1 new`).
- **UNKNOWN:** none material. The brace-style `{moved}` alternative is not used
  because the gate prints the bare count; see the claim.

## Conclusion

`test_fn_audit_scope_l3_image` now accepts the H69 moved-only form and rejects
a stale overlay, so the full suite is green again. The l3 gate and its policy
are unchanged; only the test's brittle exact string was wrong.

## Reproduction

```bash
python3 tools/selftest.py --only fn_audit_l3_image   # expected: passed=1 failed=0
python3 tools/selftest.py                           # expected: failed=0
```

## Follow-ups

- [ ] none
