# EXP-2026-11-21-H124: a clean checkout no longer reports `archive/us256.img` as missing evidence

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** `none (tool-only task)`; the board `TODO.md` and ledger
  `docs/research/claims.md` at `c4b5a902`.
- **Tools:** python3 3.11.17 / 3.15.0; `tools/claims_check.py`,
  `tools/fetch_image.py`, `tools/selftest.py`, `tools/gate.py`
- **Claims:** C-6490–C-6494
- **Supersedes:** none
- **Superseded by:** none

## Question

Why does GitHub CI (`CI quality gate`, `quality (py3.11)`) fail `claims_check`
on every pull request, including ones that touch no claim, with
`genuine missing evidence paths: 4` / `MISSING C-2141 … archive/us256.img`,
while the same command exits 0 in a developer tree?

## Hypothesis

The paths are vendor data that a clean clone does not have; `claims_check`
exempts only `archive/head256.img` (`PINNED_HEAD_PATHS`). H62 gave the US head
the `US256` fetch key and pinned its SHA-256 in `tools/fetch_image.py`, but the
claims tool's exemption list was never extended. **Falsifier:** with `US256`
in the exemption list a clone without `archive/` still reports the four rows,
or the local tree (which has the file) changes verdict.

## Inputs

| Item | Value |
| --- | --- |
| Board / ledger | `TODO.md`, `docs/research/claims.md` at `c4b5a902` |
| Head that is missing | `archive/us256.img` (US 2011, first 256 MiB) |
| Pin | `tools/fetch_image.py` `("US", "256M")` → `70d945d8…04da` |
| Tool | `tools/claims_check.py` (`PINNED_HEAD_PATHS`, `evidence_path_class`) |

## Method

1. **Sample.** `origin/main` at `c4b5a902`; the four rows are C-2141, C-2143,
   C-2144, C-2145 (M9.10).
2. **Commands.** A clone of the branch carries no `archive/` bytes (only the
   tracked `.gitkeep`), which is what the CI runner sees:
   ```bash
   git clone . ../ci-checkout && cd ../ci-checkout
   python3 tools/claims_check.py --strict --count-check; echo $?
   ```
3. **Controls.** *Positive:* the developer worktree, where
   `archive/us256.img` exists, exits 0 with `genuine missing evidence paths: 0`
   both before and after the change. *Negative:* the same clone with the
   pre-change `tools/claims_check.py` exits 1 with the four `MISSING` rows.
4. **Scope.** `tools/claims_check.py` only (`PINNED_HEAD_PATHS` gains
   `archive/us256.img`, the comment names H62's key, and `--selftest` gains an
   assertion that both pinned heads map to a real `fetch_image` key).
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Same clone, no `archive/` bytes, pre-change tool:

```
genuine missing evidence paths: 4
  MISSING C-2141 archive/us256.img
  MISSING C-2143 archive/us256.img
  MISSING C-2144 archive/us256.img
  MISSING C-2145 archive/us256.img
exit=1
```

Same clone, post-change tool:

```
genuine missing evidence paths: 0
claims_check: OK
exit=0
```

In the developer worktree (file present) both versions exit 0, so the change
does not weaken any local verdict. `python3 tools/claims_check.py --selftest`
is `OK (51 checks)`; `python3 tools/selftest.py --only claims_check` is
`passed=1 failed=0`; `python3 tools/gate.py` is `4 pass, 0 fail, 0 skip`.

## Interpretation

- **FACT:** the four rows name a file that is vendor data with a fetch key
  (`US256`) and a pinned SHA-256, i.e. a re-creatable reference, exactly like
  `archive/head256.img` (`IMG256`) after H62.
- **FACT:** the exemption lives in `claims_check`, so the failure was a missing
  entry there, not a defect in M9.10's rows.
- **OBSERVED:** `archive:us256` is now classified `vendor-pin`; the exemption
  is keyed on the path, so any future row citing the head is covered.
- **UNKNOWN:** whether the owner wants `main` branch protection to make this
  class of red impossible to merge over (H98).

## Conclusion

`PINNED_HEAD_PATHS` lists both fetchable heads; a clean checkout matches the
developer tree and GitHub CI's `claims_check` gate can be green again. Claims
C-6490–C-6494.

## Overtaken by a later commit

none

## Reproduction

```bash
git clone . /tmp/opencode/ci-checkout && ( cd /tmp/opencode/ci-checkout && python3 tools/claims_check.py --strict --count-check; echo $? )
```

## Follow-ups

- [ ] H98: branch protection / `--premerge`, so a red `main` cannot be merged
  over again (the `MISSING` class existed for ~7 h on `main`).
