# EXP-2026-11-24-H147-patch-lint-name

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** `tools/qemu-ze0/patches/ze0-m223-sd-fixed-pwd.patch`, SHA-256 `07618d138d6b9fa74e8965f59f86755d4ecd24796834ec2c4808426d44ebde7b` (bytes unchanged across the rename)
- **Tools:** bash, git 2.x (`git mv`), python3 3.15.0, repo tools `tools/qemu-ze0/build.sh`, `tools/ze0_sdlock_model.py`, `tools/claims_check.py`, `tools/todo_check.py`, `tools/board.py`
- **Claims:** C-10350–C-10352
- **Supersedes:** none
- **Superseded by:** none

## Question

Why does the `ze0 patch series still applies` job fail on `main`, and does renaming the offending patch fix it without changing any patch bytes?

## Hypothesis

`tools/qemu-ze0/build.sh`'s patch-name lint accepts `ze0-NNNN-<slug>.patch` or `ze0-hNN-<slug>.patch`; `ze0-m223-sd-fixed-pwd.patch` matches neither, so `--selftest` reports `92 passed, 2 failed` and the CI job is red. Renaming it to the next free number `ze0-0020-sd-fixed-pwd.patch` (series ends at `0019`) should make the lint pass with unchanged content. Falsifier: the selftest still reports a BAD NAME, the renamed file's SHA-256 differs, or a tool still cites the old path.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/qemu-ze0/patches/ze0-m223-sd-fixed-pwd.patch` |
| SHA-256 | `07618d138d6b9fa74e8965f59f86755d4ecd24796834ec2c4808426d44ebde7b` |
| Offset(s) / VA(s) | n/a |
| Tool / version | bash, git mv, python3 3.15.0 |
| Repo tool | `tools/qemu-ze0/build.sh` (the lint and selftest), `tools/ze0_sdlock_model.py` |

## Method

1. **Sample and hash.** The committed patch file; SHA-256 above, recorded before and after the rename.
2. **Commands.**
   ```bash
   bash tools/qemu-ze0/build.sh --selftest
   git mv tools/qemu-ze0/patches/ze0-m223-sd-fixed-pwd.patch tools/qemu-ze0/patches/ze0-0020-sd-fixed-pwd.patch
   sha256sum tools/qemu-ze0/patches/ze0-0020-sd-fixed-pwd.patch
   bash tools/qemu-ze0/build.sh --selftest
   python3 tools/ze0_sdlock_model.py --selftest
   grep -rn 'ze0-m223-sd-fixed-pwd' --include='*.py' --include='*.md' --include='*.sh' .
   ```
3. **Controls.** *Positive*: after the rename the lint prints `0 bad` and `--selftest` reports `94 passed, 0 failed`. *Negative*: before the rename the same command reports `92 passed, 2 failed` with `lint: BAD NAME`; the patch hash is identical before and after, so the only variable is the filename.
4. **Scope.** One patch rename plus reference edits in `tools/ze0_sdlock_model.py`, EXP-M2.23/M2.24/M8.H9 and two claim rows (C-8050, C-7067). No patch content, lint rule, other patch names or gate semantics were changed; QEMU was not rebuilt from source in this pass (the lint is the failing check).
5. **Falsifier.** See Hypothesis.

## Observations

```text
$ bash tools/qemu-ze0/build.sh --selftest                    # before
selftest: 92 passed, 2 failed
FAIL lint real series: exit 1, expected 0
lint: BAD NAME ze0-m223-sd-fixed-pwd.patch (want ze0-NNNN-<slug>.patch or ze0-hNN-<slug>.patch)

$ sha256sum ...ze0-m223-sd-fixed-pwd.patch
07618d138d6b9fa74e8965f59f86755d4ecd24796834ec2c4808426d44ebde7b

$ git mv ...ze0-m223-sd-fixed-pwd.patch ...ze0-0020-sd-fixed-pwd.patch
$ sha256sum ...ze0-0020-sd-fixed-pwd.patch
07618d138d6b9fa74e8965f59f86755d4ecd24796834ec2c4808426d44ebde7b

$ bash tools/qemu-ze0/build.sh --selftest                    # after
selftest: 94 passed, 0 failed                                # lint real series: 0 bad

$ python3 tools/ze0_sdlock_model.py --selftest
sd-fixed-pwd selftest: 12 checks, 0 failed
```

The only remaining `ze0-m223-sd-fixed-pwd` strings are historical (the H147 task block, the explanatory notes in EXP-M2.23/M2.24/M8.H9 and C-7067's body) — each now carries an explicit "renamed by H147, bytes unchanged" note.

## Interpretation

- **FACT:** the lint failure was purely a filename-shape violation, not a patch-content or build failure.
- **FACT:** renaming to `ze0-0020-sd-fixed-pwd.patch` clears both lint failures (`94 passed, 0 failed`) with an identical SHA-256.
- **OBSERVED:** `tools/ze0_sdlock_model.py` and the EXP/claim references now point at the new path.
- **UNKNOWN:** none for this task.

## Conclusion

The `ze0 patch series still applies` job's selftest is green on this branch; the patch content is byte-identical to M2.23's original. Historical prose that mentions the old name now records the rename, so a reader is not misled.

## Overtaken by a later commit

none

## Reproduction

```bash
bash tools/qemu-ze0/build.sh --selftest                       # expected: 94 passed, 0 failed
sha256sum tools/qemu-ze0/patches/ze0-0020-sd-fixed-pwd.patch  # expected: 07618d13…ebde7b
python3 tools/ze0_sdlock_model.py --selftest                  # expected: 12 checks, 0 failed
```

## Follow-ups

- [ ] None.
